(ns cljgen.pp
  "Indent-aware pretty printer for EDN values (Clojure port of cljgen.py's
  pp). One-line rendering delegates to cljgen.emit/emit."
  (:require [cljgen.emit :as e]))
(declare pp-seq pp-map)
(defn pp
  "Render x assuming the cursor sits at column col, wrapping at width chars.
  A list/vector/map that fits on one line is emitted as-is (cljgen.emit/emit);
  otherwise its children break onto lines indented 2 spaces per nesting level,
  and the closing delimiter sits on its own line at the opening column."
  [x col width]
  (cond
    (list? x) (pp-seq x col width)
    (vector? x) (pp-seq x col width)
    (map? x) (pp-map x col width)
    :else (e/emit x)))
(defn- pp-seq [x col width]
  (let [op (if (list? x) "(" "[")
        cl (if (list? x) ")" "]")
        ind (apply str (repeat (+ col 2) " "))
        one (e/emit x)]
    (if (or (empty? x) (<= (+ col (count one)) width))
      one
      (str op "\n"
           (apply str (interpose "\n"
                         (map (fn [c] (str ind (pp c (+ col 2) width))) x)))
           "\n" (apply str (repeat col " ")) cl))))
(defn- pp-map [x col width]
  (let [ind (apply str (repeat (+ col 2) " "))
        one (e/emit x)]
    (if (or (empty? x) (<= (+ col (count one)) width))
      one
      (str "{\n"
           (apply str (interpose "\n"
                         (map (fn [[k v]] (let [ek (e/emit k)]
                                             (str ind ek " "
                                                  (pp v (+ col 2 (count ek) 1) width)))) x)))
           "\n" (apply str (repeat col " ")) "}"))))
