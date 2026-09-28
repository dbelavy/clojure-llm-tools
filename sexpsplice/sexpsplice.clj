#!/usr/bin/env bb
; sexpsplice - structural S-expression editor for .clj/.edn files.
; Treats a file as a nested S-expression tree. An LLM (or human) supplies ONE
; replacement form on stdin and addresses the target by a PATH (a vector of
; selectors). The tool parses with a real reader (rewrite-clj) and splices it
; in, preserving every untouched byte: comments, reader macros, formatting.
;
; Commands:
;   sexpsplice list   <file>               print top-level forms, indexed 0..N
;   sexpsplice get    <file> <path>        print the node at PATH (full text)
;   sexpsplice set    <file> <path>        replace node at PATH with ONE form from stdin
;   sexpsplice append <file>               append ONE form from stdin (top-level)
;   sexpsplice delete <file> <path>        remove the node at PATH
;   sexpsplice apply  <file>               apply a batch of edits from stdin (EDN)
;   sexpsplice find   <file> <substring>   list top-level forms containing substring
;   sexpsplice move   <file> <from> <to>   move top-level form FROM to final index TO
;   sexpsplice insert <file> <idx>         insert ONE form from stdin at index IDX
;
; PATH syntax: a vector of selectors, each applied to descend one level.
;   integer  -> the Nth "value child" (non-whitespace, non-comment child), 0-based
;   keyword  -> the value of key :k in a map (descends to the value node)
;
; A bare integer path arg is shorthand for [n] (backward compatible).
;
; apply batch (stdin, EDN vector of ops):
;   [{:op :set :path [2] :form "(def beta 43)"}
;    {:op :append :form "(def delta 1)"}
;    {:op :delete :path [3]}]
; All ops apply atomically: any error -> no write, exit 1.
;
; Flags (may appear before or after the command):
;   --dry-run | -n   compute + print the result, do NOT write
;   --no-backup      skip the .bak backup
;
; Invariants:
;   - set/delete/append/apply preserve every untouched byte.
;   - move/insert preserve form content + leading comments byte-for-byte but
;     canonicalize top-level inter-form separators to single newlines.
;   - every write is atomic (temp file + rename) and backs up to <file>.bak.

(require '[rewrite-clj.zip :as z]
         '[rewrite-clj.node :as n]
         '[rewrite-clj.parser :as p]
         '[clojure.edn :as edn]
         '[clojure.string :as str])

(import '[java.nio.file Files Paths StandardCopyOption CopyOption])

(def ^:dynamic *dry-run* false)
(def ^:dynamic *no-backup* false)

;; ---- parsing ---------------------------------------------------------------

(defn parse-file [file]
  (try
    (z/of-string* (slurp file))
    (catch Exception _
      (println (str "ERROR: cannot parse file " file))
      (System/exit 1))))

(defn parse-one-form [s]
  ;; Parse a string; return a node containing exactly one form, or nil.
  (try
    (let [node (p/parse-string-all s)
          kids (remove n/whitespace? (n/children node))]
      (when (= 1 (count kids)) (first kids)))
    (catch Exception _ nil)))

(defn read-stdin-form! []
  (let [f (parse-one-form (slurp *in*))]
    (when (nil? f)
      (println "ERROR: no readable form on stdin")
      (System/exit 1))
    f))

;; ---- zipper navigation -----------------------------------------------------

;; A "value child" is a child that is neither whitespace nor comment. At every
;; level of the tree, value children are separated by whitespace/comment nodes,
;; so navigation by value-child-index must skip those.

(defn nth-value-child [loc i]
  ;; Move to the i-th value child (0-based) of loc's children, or nil.
  ;; Unstarred z/right skips whitespace and comments.
  (loop [l (z/down loc) n 0]
    (cond
      (nil? l) nil
      (= n i) l
      :else    (recur (z/right l) (inc n)))))

(defn map-value [loc k]
  ;; For a map node at loc, descend to the value node associated with key k, or nil.
  (loop [l (z/down loc)]
    (cond
      (nil? l) nil
      (and (keyword? (z/sexpr l)) (= k (z/sexpr l)))
      (z/right l)
      :else (recur (z/right l)))))

(defn resolve-path [loc selectors]
  ;; Return the loc at PATH relative to loc, or nil if the path doesn't resolve.
  (loop [l loc sels (seq selectors)]
    (if (empty? sels)
      l
      (let [sel (first sels)
            next (cond
                   (integer? sel) (nth-value-child l sel)
                   (keyword? sel) (map-value l sel)
                   :else nil)]
        (when next (recur next (rest sels)))))))

;; ---- top-level block model (for move/insert) --------------------------------

(defn form? [node]
  (and (not (n/whitespace? node)) (not (n/comment? node))))

(defn form-blocks [forms-node]
  ;; Split the FormsNode into a vector of blocks. Each block is a vector of
  ;; nodes: [leading-comments..., form]. A comment attaches to the FOLLOWING
  ;; form (doc convention). Whitespace is dropped (move/insert canonicalize
  ;; separators). Trailing comments with no following form become a final block.
  (let [kids (vec (n/children forms-node))]
    (loop [i 0 leading [] blocks []]
      (if (>= i (count kids))
        (if (seq leading)
          (conj blocks (vec leading))
          blocks)
        (let [k (nth kids i)]
          (cond
            (form? k)       (recur (inc i) [] (conj blocks (vec (concat leading [k]))))
            (n/comment? k)  (recur (inc i) (conj leading k) blocks)
            :else           (recur (inc i) leading blocks)))))))

(defn emit-string [blocks]
  ;; Render blocks as source: single-newline separators + one trailing newline.
  (let [sep (n/newlines 1)
        flat (vec (concat (apply concat (interpose [sep] blocks)) [sep]))]
    (str/join "" (map n/string flat))))

;; ---- serialization / writes -------------------------------------------------

(defn backup! [file]
  ;; Best-effort copy of file -> file.bak (the last-known-good state).
  (try
    (let [src (Paths/get file (into-array String []))
          dst (Paths/get (str file ".bak") (into-array String []))]
      (when (Files/exists src (into-array java.nio.file.LinkOption []))
        (Files/copy src dst (into-array CopyOption [StandardCopyOption/REPLACE_EXISTING]))))
    (catch Exception _ nil)))

(defn atomic-write! [file content]
  ;; Write to a temp file in the same dir, then rename over the target
  ;; (ATOMIC_MOVE where supported) so readers never see a torn write.
  (let [target (Paths/get file (into-array String []))
        dir    (or (.getParent target) (Paths/get "." (into-array String [])))
        tmp    (Files/createTempFile dir ".sexpsplice-" ".tmp" (into-array java.nio.file.attribute.FileAttribute []))]
    (try
      (Files/write tmp (.getBytes content "UTF-8") (into-array java.nio.file.OpenOption []))
      (try
        (Files/move tmp target (into-array CopyOption [StandardCopyOption/REPLACE_EXISTING
                                                        StandardCopyOption/ATOMIC_MOVE]))
        (catch Exception _
          (Files/move tmp target (into-array CopyOption [StandardCopyOption/REPLACE_EXISTING]))))
      (finally
        (Files/deleteIfExists tmp)))))

(defn commit! [file content]
  (if *dry-run*
    (do (println (str "DRY-RUN (no write) " file ":"))
        (print content)
        (when-not (str/ends-with? content "\n") (newline)))
    (do (when-not *no-backup* (backup! file))
        (atomic-write! file content))))

;; ---- commands --------------------------------------------------------------

(defn parse-path [s]
  ;; Parse a path arg: a bare integer -> [n]; otherwise EDN vector.
  (try
    (let [v (edn/read-string s)]
      (cond (integer? v) [v]
            (vector? v) v
            :else nil))
    (catch Exception _ nil)))

(defn parse-int [s]
  (try (Integer/parseInt s) (catch Exception _ nil)))

(defn preview [s]
  (let [t (str/trim s)]
    (if (> (count t) 60) (subs t 0 60) t)))

(defn say-ok [msg]
  (println (str (if *dry-run* "DRY-RUN: " "OK: ") msg)))

(defn cmd-list [file]
  (let [loc (parse-file file)]
    (loop [l (z/down loc) i 0]
      (when l
        (println (format "%d  %s" i (preview (z/string l))))
        (recur (z/right l) (inc i))))))

(defn cmd-get [file path]
  (let [loc (resolve-path (parse-file file) path)]
    (when (nil? loc)
      (println (format "ERROR: path %s does not resolve in %s" (pr-str path) file))
      (System/exit 1))
    (println (z/string loc))))

(defn cmd-set [file path]
  (let [root (parse-file file)
        loc  (resolve-path root path)]
    (when (nil? loc)
      (println (format "ERROR: path %s does not resolve in %s" (pr-str path) file))
      (System/exit 1))
    (let [new-node (read-stdin-form!)
          new-loc  (z/replace loc new-node)]
      (commit! file (z/root-string new-loc))
      (say-ok (format "replaced %s in %s" (pr-str path) file)))))

(defn cmd-delete [file path]
  (let [root (parse-file file)
        loc  (resolve-path root path)]
    (when (nil? loc)
      (println (format "ERROR: path %s does not resolve in %s" (pr-str path) file))
      (System/exit 1))
    (let [new-loc (z/remove loc)]
      (commit! file (z/root-string new-loc))
      (say-ok (format "deleted %s from %s" (pr-str path) file)))))

(defn append-node-to [forms new-node]
  ;; Append new-node to the FormsNode, byte-preserving everything before it.
  (let [kids     (vec (n/children forms))
        kids'    (loop [k kids]
                   (if (and (seq k) (n/whitespace? (peek k))) (recur (pop k)) k))
        new-kids (if (empty? kids')
                   [new-node (n/newlines 1)]
                   (conj kids' (n/newlines 1) new-node (n/newlines 1)))]
    (n/replace-children forms new-kids)))

(defn cmd-append [file]
  (let [root     (parse-file file)
        new-node (read-stdin-form!)
        nforms   (loop [l (z/down root) c 0] (if l (recur (z/right l) (inc c)) c))
        out      (str (n/string (append-node-to (z/node root) new-node)))]
    (commit! file out)
    (say-ok (format "appended as form %d in %s" nforms file))))

(defn to-root [loc]
  ;; Walk up to the root loc (z/root returns a node, not a loc; z/up returns a loc).
  (loop [l loc]
    (if (z/up l) (recur (z/up l)) l)))

(defn append-to [loc node]
  (z/of-node (append-node-to (z/node loc) node)))

(defn apply-op [loc {:keys [op path form]}]
  ;; NOTE: every branch returns (to-root ...) so each op resolves its path
  ;; against the ROOT loc, not against the previous op's result loc.
  (to-root
   (case op
     :set    (let [l (resolve-path loc path)]
               (when (nil? l) (throw (ex-info (str "path " (pr-str path) " does not resolve") {})))
               (z/replace l (parse-one-form form)))
     :delete (let [l (resolve-path loc path)]
               (when (nil? l) (throw (ex-info (str "path " (pr-str path) " does not resolve") {})))
               (z/remove l))
     :append (append-to loc (parse-one-form form))
     (throw (ex-info (str "unknown op " op) {})))))

(defn cmd-apply [file]
  (let [ops (try (edn/read-string (slurp *in*)) (catch Exception _ nil))]
    (when-not (vector? ops)
      (println "ERROR: apply expects an EDN vector of ops on stdin")
      (System/exit 1))
    (let [root (parse-file file)
          out  (try (reduce apply-op root ops)
                    (catch Exception e
                      (println "ERROR:" (.getMessage e))
                      (System/exit 1)))]
      (commit! file (z/root-string out))
      (say-ok (format "applied %d edits to %s" (count ops) file)))))

(defn cmd-find [file q]
  (let [root (parse-file file)
        ql   (str/lower-case q)
        hits (loop [l (z/down root) i 0 acc []]
               (if (nil? l)
                 acc
                 (let [s (z/string l)
                       acc (if (str/includes? (str/lower-case s) ql)
                             (conj acc [i s]) acc)]
                   (recur (z/right l) (inc i) acc))))]
    (if (empty? hits)
      (do (println (format "no match for %s in %s" (pr-str q) file))
          (System/exit 1))
      (doseq [[i s] hits]
        (println (format "%d  %s" i (preview s)))))))

(defn cmd-move [file from to]
  (let [root   (parse-file file)
        blocks (form-blocks (z/node root))
        n      (count blocks)]
    (when (or (neg? from) (>= from n) (neg? to) (>= to n))
      (println (format "ERROR: move index out of range (have %d forms)" n))
      (System/exit 1))
    (if (= from to)
      (println "OK: no-op (from == to)")
      (let [blk    (nth blocks from)
            rest   (vec (concat (subvec blocks 0 from) (subvec blocks (inc from))))
            result (vec (concat (subvec rest 0 to) [blk] (subvec rest to)))]
        (commit! file (emit-string result))
        (say-ok (format "moved form %d -> %d in %s" from to file))))))

(defn cmd-insert [file idx]
  (let [root   (parse-file file)
        blocks (form-blocks (z/node root))
        n      (count blocks)]
    (when (or (neg? idx) (> idx n))
      (println (format "ERROR: insert index %d out of range 0-%d" idx n))
      (System/exit 1))
    (let [new-node (read-stdin-form!)
          result   (vec (concat (subvec blocks 0 idx) [[new-node]] (subvec blocks idx)))]
      (commit! file (emit-string result))
      (say-ok (format "inserted at index %d in %s" idx file)))))

(defn usage []
  (println (str/join "\n"
    ["Usage: sexpsplice [--dry-run|-n] [--no-backup] <command> <file> [args...]"
     ""
     "Commands:"
     "  list   <file>               list top-level forms (index + 60-char preview)"
     "  get    <file> <path>        print the node at PATH (full text)"
     "  set    <file> <path>        replace node at PATH with ONE form from stdin"
     "  append <file>               append ONE form from stdin"
     "  delete <file> <path>        remove the node at PATH"
     "  apply  <file>               batch of edits from stdin (EDN vector, atomic)"
     "  find   <file> <substring>   list forms containing substring (case-insensitive)"
     "  move   <file> <from> <to>   move top-level form FROM to final index TO"
     "  insert <file> <idx>         insert ONE form from stdin at index IDX"
     ""
     "PATH = vector of selectors (integer = Nth value child, keyword = map key)."
     "A bare integer is shorthand for [n]."
     ""
     "Flags: --dry-run/-n prints instead of writing; --no-backup skips .bak backup."]))
  (System/exit 1))

;; ---- main ------------------------------------------------------------------

(defn dispatch [args]
  (let [cmd  (first args)
        file (second args)]
    (case cmd
      "list"   (if file (cmd-list file) (usage))
      "get"    (if (and file (nth args 2 nil))
                 (if-let [p (parse-path (nth args 2))] (cmd-get file p) (usage))
                 (usage))
      "set"    (if (and file (nth args 2 nil))
                 (if-let [p (parse-path (nth args 2))] (cmd-set file p) (usage))
                 (usage))
      "delete" (if (and file (nth args 2 nil))
                 (if-let [p (parse-path (nth args 2))] (cmd-delete file p) (usage))
                 (usage))
      "append" (if file (cmd-append file) (usage))
      "apply"  (if file (cmd-apply file) (usage))
      "find"   (if (and file (nth args 2 nil)) (cmd-find file (nth args 2)) (usage))
      "move"   (if (and file (nth args 2 nil) (nth args 3 nil))
                 (let [from (parse-int (nth args 2)) to (parse-int (nth args 3))]
                   (if (and from to) (cmd-move file from to) (usage)))
                 (usage))
      "insert" (if (and file (nth args 2 nil))
                 (if-let [i (parse-int (nth args 2))] (cmd-insert file i) (usage))
                 (usage))
      (usage))))

(defn -main [& args]
  (let [flag?      #(contains? #{"--dry-run" "-n" "--no-backup"} %)
        flags      (filter flag? args)
        positional (vec (remove flag? args))]
    (binding [*dry-run*  (boolean (some #{"--dry-run" "-n"} flags))
              *no-backup* (boolean (some #{"--no-backup"} flags))]
      (dispatch positional))))

(apply -main *command-line-args*)
