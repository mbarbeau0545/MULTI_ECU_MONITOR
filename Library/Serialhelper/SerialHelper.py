"""
#  @file        main.py
#  @brief       Template_BriefDescription.
#  @details     TemplateDetailsDescription.\n
#
#  @author      mba
#  @date        jj/mm/yyyy
#  @version     1.0
"""
#------------------------------------------------------------------------------
#                                       IMPORT
#------------------------------------------------------------------------------
from serial.tools import list_ports
from typing import Optional
#------------------------------------------------------------------------------
#                                       CONSTANT
#------------------------------------------------------------------------------

# CAUTION : Automatic generated code section: Start #

# CAUTION : Automatic generated code section: End #
#------------------------------------------------------------------------------
#                                       CLASS
#------------------------------------------------------------------------------
def find_port_by_serial(serial: str) -> str:
    """
        find a virtual com port from name 
        -------
        serial (str) the name of the materiel when using usbpid list on powershell
    """
    for p in list_ports.comports():
        if p.serial_number and p.serial_number.strip() == serial:
            return p.device  # ex: "COM6"
    raise RuntimeError(f"Périphérique avec serial={serial} introuvable")

def find_port_by_location(location_substr: str) -> str:
    for p in list_ports.comports():
        if p.location and location_substr in p.location:
            return p.device
    raise RuntimeError("Introuvable")

def find_port(vid: int, pid: int, must_contain: Optional[str] = None) -> str:
    port: Optional[str] = None

    for p in list_ports.comports():
        if p.vid == vid and p.pid == pid:
            if must_contain is None:
                port = p.device
                break

            txt = f"{p.description or ''} {p.manufacturer or ''} {getattr(p, 'product', '') or ''}"
            if must_contain.lower() in txt.lower():
                port = p.device
                break

    if port is None:
        raise RuntimeError("Périphérique USB-Série introuvable (VID/PID + filtre)")
    return port

#------------------------------------------------------------------------------
#                             FUNCTION IMPLMENTATION
#------------------------------------------------------------------------------
#------------------------------------------------------------------------------
#		                    END OF FILE
#------------------------------------------------------------------------------
#--------------------------
# Function_name
#--------------------------

"""
    @brief
    @details

    @params[in]
    @params[out]
    @retval
"""

