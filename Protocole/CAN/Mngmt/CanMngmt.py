#-------------------------------------------------------------------
# Copyright (C) 2017 - KUHN SA - Electronics
# 
# This document is KUHN SA property.
# It should not be reproduced in any medium or used in any way
# without prior written consent of KUHN SA
#-------------------------------------------------------------------
""" 
 
     
    @file        CanMngmt.py
    @brief       Call get_can_interface with the right handle from 
                    DriverCanUsed enum, to get the interface library

    @author      AUDMBA
    @date        11/08/2025
    @version     1.0
"""

#-------------------------------------------------------------------
#                     Import
#-------------------------------------------------------------------
import os
from enum import IntEnum
from datetime import datetime
from typing import List, Optional
from Library.ModuleLog import MngLogFile, log


from .AbstractCAN import CANInterface
from .PeakCanMngmt import PeakCanMngmt, PeakCanConfig
from .pcSimCanMngmt import PcSimCanMngmt, PcSimCanConfig
from .VirtCanMngmt import VirtCanMngmt, VirtCanConfig
from .WaveShareCanMngmt import WaveshareCanMngmt, WaveShareCanConfig
#-------------------------------------------------------------------
#                     Constants
#-------------------------------------------------------------------
# CAUTION : Automatic generated code section: Start #

# CAUTION : Automatic generated code section: End #

#-------------------------------------------------------------------
#                     Function
#-------------------------------------------------------------------



#-------------------------------------------------------------------
#                     Class
#-------------------------------------------------------------------



#------------------------
# DriverCanUsed
#------------------------
class DriverCanUsed(IntEnum):
    DrvPeak = 0
    DrvLibrary32bit = 1
    DrvWaveShare = 2
    DrvPcSim = 3

#------------------------
# get_can_interface
#------------------------    
def get_can_interface(  f_can_drv_used:DriverCanUsed,
                        f_canlogging:bool = False, 
                        f_dirlog_path = "",
                        f_error_cb = None) ->CANInterface:
    """
        @brief      get an dll interface
        @details 

    """ 

    # mapping for abstract library
    arg_kwargs = {
        'canlogging' : f_canlogging, 
        'dir_log_path' : f_dirlog_path, 
        'error_cb' : f_error_cb    }

    # **arg_kwargs means unpack (pas to a dictionnary to var_a = 1, var_b = 2 etc)
    match f_can_drv_used:
        case DriverCanUsed.DrvPeak:
            return PeakCanMngmt(**arg_kwargs)
        case DriverCanUsed.DrvLibrary32bit:
            return VirtCanMngmt(**arg_kwargs)
        case DriverCanUsed.DrvWaveShare:
            return WaveshareCanMngmt(**arg_kwargs)
        case DriverCanUsed.DrvPcSim:
            return PcSimCanMngmt(**arg_kwargs)




                
#-------------------------------------------------------------------
#                          End of file
#-------------------------------------------------------------------

#------------------------
# FuncName
#------------------------

"""
    @brief      
    @details

    @retval    
"""
