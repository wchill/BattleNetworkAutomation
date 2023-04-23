from utils.function_fs_server import subprocess_manager


if __name__ == "__main__":
    with subprocess_manager() as gadget:
        gadget.waitForever()
