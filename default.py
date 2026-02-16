# -*- coding: utf-8 -*-
import xbmcaddon
import xbmcgui

addon = xbmcaddon.Addon()
addon_name = addon.getAddonInfo('name')

# If a user manually clicks the addon in the menu, show a small message
xbmcgui.Dialog().ok(addon_name, "Acest serviciu rulează în fundal și traduce automat subtitrările în limba română.")
