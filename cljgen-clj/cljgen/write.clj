(ns cljgen.write
  "EDN forms -> balanced .clj file. Because EDN has no list literal,
  write-forms! treats vectors as lists, except a 1-element vector of a single
  symbol (a parameter vector like [n]), which stays a vector. The whole
  output is balance-checked; the write is refused if it is unbalanced."
  (:require [cljgen.check :as chk] [cljgen.emit :as e] [cljgen.pp :as pp]))
(defn- to-form
  "x -> the same value with every vector converted to a list (EDN has no
  list literal), except a 1-element vector whose element is a symbol, which
  stays a vector (a parameter/binding vector like [n]). Recurses into
  vectors and lists; maps and other values pass through unchanged, so the
  special raw/char maps reach cljgen.emit intact."
  [x]
  (cond
    (vector? x)
    (if (and (= 1 (count x)) (symbol? (first x)))
      x
      (apply list (map to-form x)))
    (list? x) (apply list (map to-form x))
    :else x))
(defn write-forms!
  "forms: sequence of top-level EDN values. newlines truthy: each form is
  pretty-printed at column 0 (given width) and joined by blank lines, with a
  trailing newline; falsy: each form is emitted on one line and joined by a
  single space, no trailing newline. The WHOLE text is balance-checked
  before writing; if unbalanced nothing is written and
  {:ok false :error \"unbalanced\"} is returned. Otherwise path is
  created/overwritten and {:ok true :text t} is returned."
  [path forms newlines width]
  (let [fs (map to-form (seq forms))
        text (if newlines
               (str (apply str (interpose "\n\n" (map (fn [f] (pp/pp f 0 width)) fs)))
                    "\n")
               (apply str (interpose " " (map e/emit fs))))]
    (if (chk/balanced? text)
      (do (spit path text)
          {:ok true :text text})
      {:ok false :error "unbalanced"})))
