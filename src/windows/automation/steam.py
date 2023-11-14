import functools
import os
from typing import Optional

import vdf

LIBRARYFOLDERS_VDF_PATH = r"C:\Program Files (x86)\Steam\steamapps\libraryfolders.vdf"
STEAM_APPID_VOL1 = 1798010
STEAM_APPID_VOL2 = 1798020


@functools.cache
def get_game_install_paths() -> tuple[Optional[str], Optional[str]]:
    with open(LIBRARYFOLDERS_VDF_PATH, "r") as f:
        library_folders = vdf.load(f)["libraryfolders"]

    vol1_path = None
    vol2_path = None

    for folder in library_folders.values():
        if str(STEAM_APPID_VOL1) in folder["apps"]:
            vol1_path = folder["path"] + r"\steamapps\common\MegaMan_BattleNetwork_LegacyCollection_Vol1\exe"

        if str(STEAM_APPID_VOL2) in folder["apps"]:
            vol2_path = folder["path"] + r"\steamapps\common\MegaMan_BattleNetwork_LegacyCollection_Vol2\exe"

    return vol1_path, vol2_path


def get_vol1_exe_path() -> str:
    vol1_dir, _ = get_game_install_paths()
    return os.path.join(vol1_dir, "MMBN_LC1.exe")


def get_vol2_exe_path() -> str:
    _, vol2_dir = get_game_install_paths()
    return os.path.join(vol2_dir, "MMBN_LC2.exe")


def get_userdata_path(steamid_32: int) -> str:
    return rf"C:\Program Files (x86)\Steam\userdata\{steamid_32}"


def get_vol1_save_directory(steamid_32: int) -> str:
    base_path = get_userdata_path(steamid_32)
    return rf"{base_path}\1798010\remote"


def get_vol2_save_directory(steamid_32: int) -> str:
    base_path = get_userdata_path(steamid_32)
    return rf"{base_path}\1798020\remote"


def get_logged_in_user_steamid32() -> int:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\Valve\Steam\ActiveProcess") as key:
            val, reg_type = winreg.QueryValueEx(key, "ActiveUser")
            assert reg_type == winreg.REG_DWORD
            return val
    except ImportError:
        raise RuntimeError("This function can only be called on a Windows machine.")
