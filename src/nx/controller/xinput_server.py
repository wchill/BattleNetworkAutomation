from typing import Optional

import vdf

LIBRARYFOLDERS_VDF_PATH = r"C:\Program Files (x86)\Steam\steamapps\libraryfolders.vdf"
STEAM_APPID_VOL1 = 1798010
STEAM_APPID_VOL2 = 1798020


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
