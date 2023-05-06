from bn_automation.controller.function_fs_server import subprocess_manager


def start_server():
    with subprocess_manager() as gadget:
        gadget.waitForever()


if __name__ == "__main__":
    start_server()
