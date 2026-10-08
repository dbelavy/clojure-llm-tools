(ns cljgen.cli
  "EDN -> .clj. Reads one EDN value from <edn-file>; a vector value is one
  form per element, any other value is a single form. Writes pretty output
  (width 80) to <target.clj> via cljgen.write."
  (:require [clojure.edn :as edn] [cljgen.write :as w]))
(defn -main
  "args: <edn-file> <target.clj>. Prints 'wrote <target>' and exits 0 on
  success; prints a message to stderr and exits 1 for bad usage, bad EDN,
  a missing file, or an unbalanced result."
  [& args]
  (if (< (count args) 2)
    (do (print *err* "usage: clojure -M:cli <edn-file> <target.clj>\n")
        (.flush *err*)
        (System/exit 1))
    (let [edn-file (first args)
          target   (second args)
          v (try (edn/read-string (slurp edn-file))
                 (catch Exception ex
                   (print *err* (.getMessage ex) "\n")
                   (.flush *err*)
                   (System/exit 1)))
          forms (if (vector? v) v [v])
          r (w/write-forms! target forms true 80)]
      (if (:ok r)
        (println (str "wrote " target))
        (do (print *err* (:error r) "\n")
            (.flush *err*)
            (System/exit 1))))))
