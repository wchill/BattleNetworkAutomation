import os


def install():
    os.system("/bin/bash " + os.path.join(os.path.dirname(__file__), "install.sh"))


if __name__ == "__main__":
    install()
