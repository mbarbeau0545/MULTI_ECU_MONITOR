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
import sys
import os
from Library.PyCodeGene import LoadConfig_FromExcel as LCFE

#------------------------------------------------------------------------------
#                                       CONSTANT
#------------------------------------------------------------------------------
EMPTY_CELL = "None"
# CAUTION : Automatic generated code section: Start #

# CAUTION : Automatic generated code section: End #
#------------------------------------------------------------------------------
#                                       CLASS
#------------------------------------------------------------------------------
class SnsInfo():
    def __init__(self, f_cfgpath:str) -> None:
        self.info = {}
        self.dvc_list = []
        self.__get_info(f_cfgpath)
    #--------------------------
    # __get_info
    #--------------------------
    def __get_info(self, f_cfgpath:str) -> None:
        try:
            excel_info = LCFE()
            excel_info.load_excel_file(f_cfgpath)
            sns_interface_cfg_a = excel_info.get_array_from_excel("AppSns_SnsInterface")[1:]
            if not sns_interface_cfg_a:
                return
            if str(sns_interface_cfg_a[0][0]) != EMPTY_CELL:
                for _, sns_cfg in enumerate(sns_interface_cfg_a):
                    sns_if_name = f"{sns_cfg[0]}_{sns_cfg[1]}"
                    unity = sns_cfg[2]
                    debug_sig = sns_cfg[3]
                    self.info[sns_if_name] = {
                        "unity" : unity,
                        "signal" : debug_sig
                    }

                    if sns_cfg[0] not in self.dvc_list:
                        self.dvc_list.append(sns_cfg[0])
        except Exception:
            self.info = {}
            self.dvc_list = []



class ActInfo():
    def __init__(self, f_cfgpath:str) -> None:
        self.info = {}
        self.dvc_list = []
        self.dvc_sig = []
        self.__get_info(f_cfgpath)
    #--------------------------
    # __get_info
    #--------------------------
    def __get_info(self, f_cfgpath:str) -> None:
        try:
            excel_info = LCFE()
            excel_info.load_excel_file(f_cfgpath)
            act_interface_cfg_a = excel_info.get_array_from_excel("AppAct_ActInterface")[1:]
            if not act_interface_cfg_a:
                return
            if str(act_interface_cfg_a[0][0]) != EMPTY_CELL:
                for _, act_cfg in enumerate(act_interface_cfg_a):
                    act_if_name = f"{act_cfg[0]}_{act_cfg[1]}"
                    set_signal = act_cfg[2]
                    get_signal = act_cfg[3]
                    ctrl_signal = act_cfg[4]

                    self.info[act_if_name] = {
                        "set_sig" : set_signal,
                        "get_sig" : get_signal,
                        "ctrl_sig" : ctrl_signal
                    }

                    if act_cfg[0] not in self.dvc_list:
                        self.dvc_list.append(act_cfg[0])
        except Exception:
            self.info = {}
            self.dvc_list = []
               

        
        
#------------------------------------------------------------------------------
#                             FUNCTION IMPLMENTATION
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
#			                MAIN
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

