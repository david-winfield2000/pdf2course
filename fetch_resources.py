"""Download what the book's code and online-only content need, into the paths it expects.

    hidden/handson-mlp/.venv/bin/python fetch_resources.py

Safe to re-run. Hugging Face models and datasets (Chapters 14-18) are left out: they
total tens of GB and download themselves into ~/.cache/huggingface on first use.
"""
import os
import pathlib
import tarfile
import urllib.request
import zipfile

ROOT = pathlib.Path(__file__).parent
BOOK = ROOT / "hidden" / "handson-mlp"
GH = "https://github.com/ageron/data/raw/main/"
SPAM = "http://spamassassin.apache.org/old/publiccorpus/"
SITE = "https://ageron.github.io/homlp/HOMLP_"

ONLINE = ["Chapter_17", "Appendix_C", "Appendix_D", "Appendix_E", "Appendix_F"]
FILES = {  # path under the book repo → URL
    "datasets/lifesat/oecd_bli.csv": GH + "lifesat/oecd_bli.csv",
    "datasets/lifesat/gdp_per_capita.csv": GH + "lifesat/gdp_per_capita.csv",
    "datasets/housing.tgz": GH + "housing.tgz",
    "datasets/titanic.tgz": GH + "titanic.tgz",
    "datasets/spam/ham.tar.bz2": SPAM + "20030228_easy_ham.tar.bz2",
    "datasets/spam/spam.tar.bz2": SPAM + "20030228_spam.tar.bz2",
    "datasets/images/soccer.jpg": "https://homl.info/soccer.jpg",
    "datasets/ridership.tgz": GH + "ridership.tgz",
    "datasets/jsb_chorales.tgz": "https://homl.info/bach",
    "datasets/shakespeare/shakespeare.txt": "https://homl.info/shakespeare",
    "datasets/hymenoptera_data.zip": "https://download.pytorch.org/tutorial/hymenoptera_data.zip",
}


def get(url, path):
    if path.exists():
        return
    print("Downloading", path.name, flush=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "pdf2course"})
    with urllib.request.urlopen(request) as response, open(path.with_suffix(".part"), "wb") as f:
        f.write(response.read())
    path.with_suffix(".part").rename(path)


def extract(path):
    if path.name.endswith((".tgz", ".tar.bz2")):
        with tarfile.open(path) as tar:
            tar.extractall(path=path.parent, filter="data")
    elif path.suffix == ".zip":
        with zipfile.ZipFile(path) as z:
            z.extractall(path.parent)


def main():
    for name in ONLINE:
        get(f"{SITE}{name}.pdf", ROOT / "hidden" / "online" / f"{name}.pdf")

    os.chdir(BOOK)
    for rel, url in FILES.items():
        path = pathlib.Path(rel)
        if not path.exists():
            get(url, path)
            extract(path)

    from sklearn.datasets import fetch_california_housing, fetch_covtype, fetch_openml, get_data_home

    get(GH + "olivetti_py3.pkz", pathlib.Path(get_data_home()) / "olivetti_py3.pkz")
    print("Fetching scikit-learn datasets", flush=True)
    fetch_openml("mnist_784", as_frame=False)
    fetch_openml(name="Fashion-MNIST", as_frame=False)
    fetch_california_housing()
    fetch_covtype()

    import torchvision.datasets as tv

    print("Fetching torchvision datasets", flush=True)
    tv.MNIST(root="datasets", download=True)
    tv.FashionMNIST(root="datasets", download=True)
    tv.CIFAR10(root="datasets", download=True)
    tv.Flowers102(root="datasets", download=True)
    print("All done.")


if __name__ == "__main__":
    main()
