# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Top10NL-downloader
                                 A QGIS plugin
 Download BRT-Top10NL features via OGC-API
                             -------------------
        begin                : 2025-05-20
        copyright            : Created by Claude and wvdbee
        email                : your.email@example.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 This script initializes the plugin, making it known to QGIS.
"""

from qgis.utils import iface

# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load Top10NLDownloader class from file Top10NLDownloader.
    
    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .top10nl_downloader import Top10NLDownloader
    return Top10NLDownloader(iface)
