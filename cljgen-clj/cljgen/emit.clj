(ns cljgen.emit
  "Serialize one EDN value to balanced Clojure source (a string).")
(defn- esc [s]
  (apply str (map (fn [ch]
                    (case ch
                      \\ "\\"
                      \" "\\\""
                      \newline "\\n"
                      \tab "\\t"
                      \return "\\r"
                      \formfeed "\\f"
                      (str ch))) s)))
(defn emit
  "One value -> one-line balanced Clojure text. List -> ( ), vector -> [ ],
  map -> { k v }, string -> \"quoted\" (escapes backslash, quote, newline,
  tab, CR, formfeed), keyword -> :x, symbol bare, number/bool/nil literal,
  {:__raw__ t} -> t verbatim, {:__char__ n} -> backslash + n (a char literal),
  {:__vec__ v} -> v emitted as a vector.
  No reader is involved — emit only BUILDS the output string; balance is
  checked later by cljgen.check."
  [x]
  (cond
    (nil? x) "nil"
    (true? x) "true"
    (false? x) "false"
    (number? x) (str x)
    (string? x) (str "\"" (esc x) "\"")
    (keyword? x) (str x)
    (symbol? x) (str x)
    (and (map? x) (empty? x)) "{}"
    (and (vector? x) (empty? x)) "[]"
    (and (list? x) (empty? x)) "()"
    (map? x)
    (let [[k v] (first x)]
      (cond
        (and (= 1 (count x)) (= "__raw__" (name k)))  (str v)
        (and (= 1 (count x)) (= "__char__" (name k))) (str \\ (str v))
        (and (= 1 (count x)) (= "__vec__" (name k)))  (emit v)
        :else (str "{ " (apply str (interpose " " (mapcat (fn [[k v]] [(emit k) (emit v)]) (seq x)))) " }")))
    (vector? x) (str "[" (apply str (interpose " " (map emit (seq x)))) "]")
    (list? x) (str "(" (apply str (interpose " " (map emit (seq x)))) ")")
    :else (str "cannot emit " (class x))))
