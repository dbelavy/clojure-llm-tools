(ns cljgen.check
  "bal_ok port: balanced? verifies ( ) [ ] { } nesting, honoring string
  literals, char literals (full grammar), and ; comments.")
(def ^:private named-chars (list "newline" "space" "tab" "return" "backspace" "formfeed"))
(defn- skip-char-literal
  "s is an indexed char sequence with (nth s i) == \\. Return the index just
  past the Clojure char literal: \\x (single char), \\newline (named),
  \\uXXXX, or \\oXXX — the full grammar, not a naive 2-char skip."
  [s i]
  (let [n (count s)]
    (if (>= (inc i) n)
      (inc i)
      (if-let [name (some (fn [nm] (when (.startsWith s nm i) nm)) named-chars)]
        (+ i (count name))
        (let [c (nth s i)]
          (if (= c \u)
            (loop [j (inc i)]
              (if (and (< j n) (< j (+ i 5)) (some #{\0 \1 \2 \3 \4 \5 \6 \7 \8 \9 \a \b \c \d \e \f \A \B \C \D \E \F} (nth s j)))
                (recur (inc j))
                j))
            (if (= c \o)
              (loop [j (inc i)]
                (if (and (< j n) (< j (+ i 4)) (some #{\0 \1 \2 \3 \4 \5 \6 \7} (nth s j)))
                  (recur (inc j))
                  j))
              (inc i))))))))
(defn balanced?
  "true iff every ( ) [ ] { } in s is balanced and nested, respecting string,
  char-literal, and ; comment contents."
  [s]
  (let [n (count s)]
    (loop [i 0 stack []]
      (if (>= i n)
        (empty? stack)
        (let [c (nth s i)]
          (cond
            (= c \;) (let [j (.indexOf s (str \newline) i)]
                       (recur (if (neg? j) n j) stack))
            (= c \") (let [j (loop [j (inc i)]
                              (if (and (< j n) (not= (nth s j) \"))
                                (recur (+ j (if (= (nth s j) \\) 2 1)))
                                j))]
                       (recur (inc j) stack))
            (= c \\) (recur (skip-char-literal s i) stack)
            (contains? #{\( \[ \{} c) (recur (inc i) (conj stack c))
            (contains? #{\) \] \}} c) (if (or (empty? stack)
                                               (not= (nth "([{" (.indexOf ")]}" (str c))) (peek stack)))
                                          false
                                          (recur (inc i) (pop stack)))
            :else (recur (inc i) stack)))))))
