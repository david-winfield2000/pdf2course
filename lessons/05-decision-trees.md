# Chapter 5: Decision Trees

> Source: `hidden/HOML/05-chapter-5-decision-trees.md`

## Goals

By the end of this lesson you can:

- Train, visualize, and read a decision tree (classification and regression)
- Explain Gini impurity and how CART picks splits
- Regularize a tree with `max_depth` and `min_samples_leaf`
- Explain why trees are sensitive to rotation and have high variance

Each section loads starter code into the editor on the right. Boilerplate is filled in; you write the part marked `TODO`.

## How a tree predicts

Start at the root, answer a yes/no question about one feature, move to the child, repeat until a leaf. The leaf's class is the prediction.

- **No feature scaling needed.** Trees only compare a feature to a threshold.
- **White box:** you can read the rules, unlike forests or neural nets.
- Each node stores `samples`, `value` (instances per class), and `gini`.

![Iris tree](hidden/HOML/images/HOML.pdf-0210-08.png)

## Example 1: Train a tree on iris

Fit a depth-2 tree on petal length and width.

```python
from sklearn.datasets import load_iris
from sklearn.tree import DecisionTreeClassifier

iris = load_iris(as_frame=True)
X_iris = iris.data[["petal length (cm)", "petal width (cm)"]].values
y_iris = iris.target

tree_clf = DecisionTreeClassifier(max_depth=2, random_state=42)
tree_clf.fit(X_iris, y_iris)
```

**Your turn:** create and fit the tree, then refit with `max_depth=3` and compare depth and leaf count.

```python starter
from sklearn.datasets import load_iris
from sklearn.tree import DecisionTreeClassifier

iris = load_iris(as_frame=True)
X_iris = iris.data[["petal length (cm)", "petal width (cm)"]].values
y_iris = iris.target

# TODO 1: create a DecisionTreeClassifier (max_depth=2, random_state=42) and fit it
tree_clf = None

# TODO 2: fit a second tree with max_depth=3, then print get_depth() and get_n_leaves() for both
```

<details><summary>Solution</summary>

```python
tree_clf = DecisionTreeClassifier(max_depth=2, random_state=42).fit(X_iris, y_iris)
tree_clf3 = DecisionTreeClassifier(max_depth=3, random_state=42).fit(X_iris, y_iris)
print(tree_clf.get_depth(), tree_clf.get_n_leaves())
print(tree_clf3.get_depth(), tree_clf3.get_n_leaves())
```

</details>

## Example 2: Visualize and read the tree

The book uses Graphviz; `plot_tree` needs no extra install.

```python
import matplotlib.pyplot as plt
from sklearn.tree import plot_tree

plt.figure(figsize=(9, 5))
plot_tree(tree_clf, feature_names=["petal length (cm)", "petal width (cm)"],
          class_names=iris.target_names, rounded=True, filled=True)
plt.show()
```

**Your turn:** plot the tree, then print every node's Gini (`tree_clf.tree_.impurity`).

```python starter
import matplotlib.pyplot as plt
from sklearn.datasets import load_iris
from sklearn.tree import DecisionTreeClassifier, plot_tree

iris = load_iris(as_frame=True)
X_iris = iris.data[["petal length (cm)", "petal width (cm)"]].values
y_iris = iris.target
tree_clf = DecisionTreeClassifier(max_depth=2, random_state=42).fit(X_iris, y_iris)

plt.figure(figsize=(9, 5))
# TODO 1: call plot_tree with feature_names, class_names=iris.target_names, rounded=True, filled=True
plt.show()

# TODO 2: print the Gini impurity of every node
```

<details><summary>Solution</summary>

```python
plot_tree(tree_clf, feature_names=["petal length (cm)", "petal width (cm)"],
          class_names=iris.target_names, rounded=True, filled=True)
print(tree_clf.tree_.impurity.round(3))
```

</details>

## Example 3: Class probabilities

Probabilities are the class proportions in the leaf the instance lands in.

```python
print(tree_clf.predict_proba([[5, 1.5]]).round(3))   # [[0.    0.907 0.093]]
print(tree_clf.predict([[5, 1.5]]))                  # [1]
```

**Your turn:** predict for petals 5×1.5 cm and 6×1.5 cm. Are the probabilities the same? Why?

```python starter
from sklearn.datasets import load_iris
from sklearn.tree import DecisionTreeClassifier

iris = load_iris(as_frame=True)
X_iris = iris.data[["petal length (cm)", "petal width (cm)"]].values
tree_clf = DecisionTreeClassifier(max_depth=2, random_state=42).fit(X_iris, iris.target)

# TODO: print predict_proba (rounded to 3) for [[5, 1.5]] and [[6, 1.5]]
```

<details><summary>Solution</summary>

```python
print(tree_clf.predict_proba([[5, 1.5]]).round(3))
print(tree_clf.predict_proba([[6, 1.5]]).round(3))  # same leaf => same probabilities
```

</details>

## Gini impurity and CART

**Gini:** `G = 1 − Σ pₖ²`. It is 0 when a node holds one class only (pure). A node with class counts [0, 49, 5] has `1 − (49/54)² − (5/54)² ≈ 0.168`.

**CART** is greedy and recursive: pick the feature `k` and threshold `tₖ` that minimize the size-weighted impurity of the two child subsets, then repeat on each subset. It stops at `max_depth` or when no split reduces impurity. The result is not guaranteed optimal (finding the optimal tree is NP-complete).

- Prediction cost: `O(log₂ m)`. Training cost: `O(n · m log₂ m)`.
- Entropy is an alternative (`criterion="entropy"`); it usually makes little difference. Gini is slightly faster.

![Decision boundaries](hidden/HOML/images/HOML.pdf-0212-06.png)

## Regularization

Unconstrained trees overfit (they are *nonparametric*). Restrict them with `max_depth`, `min_samples_leaf`, `max_leaf_nodes`, `min_samples_split`, `max_features`, or `ccp_alpha` (pruning).

- `max_depth` is a good default knob.
- `min_samples_leaf` helps on small datasets.

## Example 4: Regularization on moons

An unconstrained tree overfits; `min_samples_leaf=5` generalizes better.

```python
from sklearn.datasets import make_moons

X_moons, y_moons = make_moons(n_samples=150, noise=0.2, random_state=42)

tree_clf1 = DecisionTreeClassifier(random_state=42)
tree_clf2 = DecisionTreeClassifier(min_samples_leaf=5, random_state=42)
tree_clf1.fit(X_moons, y_moons)
tree_clf2.fit(X_moons, y_moons)

X_moons_test, y_moons_test = make_moons(n_samples=1000, noise=0.2, random_state=43)
print(tree_clf1.score(X_moons_test, y_moons_test))  # book: 0.898
print(tree_clf2.score(X_moons_test, y_moons_test))  # book: 0.92
```

![Moons boundaries](hidden/HOML/images/HOML.pdf-0218-00.png)

**Your turn:** find which `min_samples_leaf` gives the best test score.

```python starter
from sklearn.datasets import make_moons
from sklearn.tree import DecisionTreeClassifier

X_moons, y_moons = make_moons(n_samples=150, noise=0.2, random_state=42)
X_moons_test, y_moons_test = make_moons(n_samples=1000, noise=0.2, random_state=43)

# TODO: loop over min_samples_leaf in [1, 3, 5, 10, 20, 40];
#       fit a tree on (X_moons, y_moons) and print the leaf size and test score
```

<details><summary>Solution</summary>

```python
for leaf in [1, 3, 5, 10, 20, 40]:
    clf = DecisionTreeClassifier(min_samples_leaf=leaf, random_state=42).fit(X_moons, y_moons)
    print(leaf, clf.score(X_moons_test, y_moons_test))
```

</details>

## Regression trees

Same structure, but each leaf predicts the *mean target* of its instances, and CART minimizes MSE instead of impurity. They overfit just like classifiers; `min_samples_leaf` fixes it.

![Regression tree](hidden/HOML/images/HOML.pdf-0219-00.png)

## Example 5: Regression tree

A depth-2 regression tree on a noisy quadratic.

```python
import numpy as np
from sklearn.tree import DecisionTreeRegressor

rng = np.random.default_rng(seed=42)
X_quad = rng.random((200, 1)) - 0.5
y_quad = X_quad ** 2 + 0.025 * rng.standard_normal((200, 1))

tree_reg = DecisionTreeRegressor(max_depth=2, random_state=42)
tree_reg.fit(X_quad, y_quad)
print(tree_reg.predict([[0.2]]))  # book: 0.038
```

**Your turn:** plot predictions for depth 2, depth 3, and unrestricted trees over the data.

```python starter
import matplotlib.pyplot as plt
import numpy as np
from sklearn.tree import DecisionTreeRegressor

rng = np.random.default_rng(seed=42)
X_quad = rng.random((200, 1)) - 0.5
y_quad = X_quad ** 2 + 0.025 * rng.standard_normal((200, 1))

xs = np.linspace(-0.5, 0.5, 500).reshape(-1, 1)
plt.scatter(X_quad, y_quad, s=8, c="gray")
# TODO: for d in [2, 3, None]: fit a DecisionTreeRegressor(max_depth=d, random_state=42)
#       and plt.plot(xs, reg.predict(xs), label=f"max_depth={d}")
plt.legend()
plt.show()
```

<details><summary>Solution</summary>

```python
for d in [2, 3, None]:
    reg = DecisionTreeRegressor(max_depth=d, random_state=42).fit(X_quad, y_quad)
    plt.plot(xs, reg.predict(xs), label=f"max_depth={d}")
```

</details>

## Limitations

- **Axis-aligned splits:** rotating the data can make the boundary convoluted. Scaling + PCA often helps.
- **High variance:** small data or hyperparameter changes give very different trees. Averaging many trees (a random forest, next chapter) fixes this.

![Rotation sensitivity](hidden/HOML/images/HOML.pdf-0221-01.png)

## Example 6: Rotation and PCA

Scaling + PCA rotates the data so one feature can separate the classes.

```python
from sklearn.decomposition import PCA
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

pca_pipeline = make_pipeline(StandardScaler(), PCA())
X_iris_rotated = pca_pipeline.fit_transform(X_iris)
tree_clf_pca = DecisionTreeClassifier(max_depth=2, random_state=42)
tree_clf_pca.fit(X_iris_rotated, y_iris)
```

**Your turn:** compare the training accuracy of a `max_depth=1` tree on raw versus rotated features.

```python starter
from sklearn.datasets import load_iris
from sklearn.decomposition import PCA
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

iris = load_iris(as_frame=True)
X_iris = iris.data[["petal length (cm)", "petal width (cm)"]].values
y_iris = iris.target

# TODO 1: build a pipeline of StandardScaler() and PCA(); fit_transform X_iris into X_iris_rotated
X_iris_rotated = None

# TODO 2: for raw and rotated features, fit a max_depth=1 tree and print its training score
```

<details><summary>Solution</summary>

```python
pca_pipeline = make_pipeline(StandardScaler(), PCA())
X_iris_rotated = pca_pipeline.fit_transform(X_iris)
for name, X in [("raw", X_iris), ("rotated", X_iris_rotated)]:
    clf = DecisionTreeClassifier(max_depth=1, random_state=42).fit(X, y_iris)
    print(name, clf.score(X, y_iris))
```

</details>

## Exercise: Grow a forest

Book exercises 7–8: tune a tree on moons, then majority-vote 1,000 trees trained on small subsets. Expect ~85–87% for the tuned tree and 0.5–1.5% better for the vote.

```python starter
import numpy as np
from scipy.stats import mode
from sklearn.base import clone
from sklearn.datasets import make_moons
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GridSearchCV, ShuffleSplit, train_test_split
from sklearn.tree import DecisionTreeClassifier

X, y = make_moons(n_samples=10000, noise=0.4, random_state=42)
X_train, X_test, y_train, y_test = train_test_split(X, y, random_state=42)

# TODO 1: GridSearchCV over max_leaf_nodes (2..99); print best params and test accuracy

# TODO 2: ShuffleSplit with 1000 splits of train_size=100; train a clone of the best tree on each
#         subset and collect the predictions on X_test

# TODO 3: majority vote with scipy.stats.mode(preds, axis=0); print its accuracy
```

<details><summary>Solution</summary>

```python
grid = GridSearchCV(DecisionTreeClassifier(random_state=42),
                    {"max_leaf_nodes": list(range(2, 100)), "min_samples_split": [2, 3, 4]},
                    cv=3).fit(X_train, y_train)
print(grid.best_params_, grid.score(X_test, y_test))

splits = ShuffleSplit(n_splits=1000, train_size=100, random_state=42)
preds = np.array([clone(grid.best_estimator_).fit(X_train[i], y_train[i]).predict(X_test)
                  for i, _ in splits.split(X_train)])
y_vote = mode(preds, axis=0).mode.ravel()
print(accuracy_score(y_test, y_vote))
```

</details>

## Wrap-up

**Applying it:** use a tree when predictions must be explainable (credit decisions, triage) or as a quick baseline needing no preprocessing. Try `max_depth=3` on a tabular dataset of your own and read the rules.

**Pitfalls:**

- Leaving `max_depth` unlimited and trusting the training score.
- Forgetting `random_state`: the same data can give a different tree.
- Expecting smooth or rotated boundaries; trees only make axis-aligned cuts.

**Recap:**

- Trees ask one yes/no question per node; no scaling needed.
- CART greedily minimizes weighted Gini (classification) or MSE (regression).
- Regularize with `max_depth` / `min_samples_leaf`.
- Trees are interpretable but high variance; forests fix that.

## Review Questions

1. What does `gini=0` mean for a node? — All its training instances are one class.
2. Why is CART called greedy? — It picks the best split at each node without looking ahead.
3. What does a regression leaf predict? — The mean target of its training instances.
4. Why can PCA help a tree? — It rotates data so splits align with the axes.
5. Why do random forests help? — Averaging many trees reduces variance.
