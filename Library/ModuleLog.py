#################################################################################
#  @file        ModuleLog.py
#  @brief       Manage to create log file and complete them.\n
#  @details     This module allows the client to :
#               - Init one or more files
#               - Send a msg into a particular file
#               - Create a filter to print only error critical etc
#               - Create a file for only put data in it
#               - excel File ?
#               - HTML file ?
#
#  @author      AUDMBA
#  @date        10/01/2024
#  @version     1.0
################################################################################
#                                       IMPORT
################################################################################
import logging as log
from datetime import datetime
from logging.handlers import RotatingFileHandler

################################################################################
#                                       DEFINE
################################################################################
IsModuleOn_b:bool = False
###################
#constant to use 
###################
CRITICAL = 50
FATAL = CRITICAL
ERROR = 40
WARNING = 30
WARN = WARNING
INFO = 20
DEBUG = 10
NOTSET = 0

_levelToName = {
    CRITICAL: 'CRITICAL',
    ERROR: 'ERROR',
    WARNING: 'WARNING',
    INFO: 'INFO',
    DEBUG: 'DEBUG',
    NOTSET: 'NOTSET',
}
################################################################################
#                                       CLASS
################################################################################
##########################
# Start Class MngLogFile
##########################
class MngLogFile():
    def __init__(self, f_folder_path:str, f_fileName, f_level:int, f_PurposeFile:str):
        global IsModuleOn_b
        if not all((isinstance(f_folder_path,str), isinstance(f_level,int),isinstance(f_fileName,str),isinstance(f_PurposeFile,str))):
                   raise TypeError("Arg Invalid")
        self.FolderPath = f_folder_path
        self.FileName = f_fileName
        self.LevelInfo = f_level
        self.Purpose = f_PurposeFile
        self._LCF_InitFileTmpl()
        IsModuleOn_b = True
        return 
    ##########################
    # _LCF_InitFileTmpl
    ##########################
    def _LCF_InitFileTmpl(self): 
        """
            @brief    Make the file look prettier, make a frontpage, 
        """
        #verify entry
        actual_time = datetime.now()
        formated_date = actual_time.strftime("%Y-%m-%d")
        startFile = ("##########################################################################\n"
                    f"#  @file              {self.FileName}\n"
                    f"#  @brief             This document purpose is for {self.Purpose} .\n"
                    "#  @author            AUDMBA\n"
                    f"#  @Last Update       {formated_date}\n"
                    "############################################################################\n\n")

        log_file_path = self.FolderPath + "//" + self.FileName
        # Ouvrez le fichier en mode écriture et écrivez l'en-tête
        with open(log_file_path, 'w') as file:
            file.write(startFile)

        return
    ##########################
    # LCF_SetMsgLog
    ##########################
    def LCF_SetMsgLog(self, f_level:int, f_msg, f_data=None):
        """
            @brief  Allow the user to put msg and data on the logfile
        """
        log_file_path:str
        level_str:str = _levelToName[INFO]
        if not all((isinstance(f_level, int), isinstance(self.FileName, str))):
            raise TypeError("Arg Invalid")
        if not (IsModuleOn_b):
            raise Exception("Module not initialized")

        log_file_path = self.FolderPath + "//" + self.FileName
        actual_time = datetime.now()
        formated_date = actual_time.strftime("%Y-%m-%d %H:%M:%S")

        if(f_level in _levelToName):
            level_str = _levelToName[f_level]
        else:
            level_str = _levelToName[INFO]
            
        msg_to_write_str = formated_date + " "+ f"[{level_str}]" + " " + f_msg

        if(f_data != None):
            msg_to_write_str += f": {f_data}\n"
        else:
            msg_to_write_str += "\n"
        # Ouvrez le fichier en mode écriture
        with open(log_file_path, 'a+') as file:
            file.write(msg_to_write_str)
        return 
    ##############################
    # LCF_SortPerLevel
    ##############################
    def LCF_SortPerLevel(self,f_NewfileName:str, f_level:log):
        """
            @brief  Make a new file to sort a huge file by level
        """
        level_str:str = _levelToName[INFO]
        if not all ((isinstance(f_level, int), isinstance(f_NewfileName, str))):
            raise TypeError("Arg Invalid")
        if not(IsModuleOn_b):
            raise Exception("Module not initialized")

        #change log:int into an str 
        if(f_level in _levelToName):
            level_str = _levelToName[f_level]

        actual_time = datetime.now()
        formated_date = actual_time.strftime("%Y-%m-%d")
        startFile = ("##########################################################################\n"
                    f"#  @file              {f_NewfileName}\n"
                    f"#  @brief             This document purpose is for {level_str} category.\n"
                    "#  @author            AUDMBA\n"
                    f"#  @Last Update       {formated_date}\n"
                    "############################################################################\n\n")

        with open(f"{self.FolderPath}/log_{level_str}.log", "w") as file_writing:
            file_writing.write(startFile)

        with open(f"{self.FolderPath}/{self.FileName}", "r") as file_extraction:
                    for line in file_extraction:
                        if(f"{level_str}" in line):
                            with open(f"{self.FolderPath}/log_{level_str}.log", "a+") as file_writing:
                                file_writing.write(line )
        return 
##########################
# END Class MngLogFile
##########################
################################################################################
#                                 FUNCTION DECLARATION
################################################################################



################################################################################
#                             FUNCTION IMPLEMENTATION
################################################################################







################################################################################
#			                    EXAMPLE
################################################################################

"""PrintLog = MngLogFile("Doc//Log","filey.log",log.DEBUG,"print things")
PrintLog.LCF_SetMsgLog(log.DEBUG,"Je suis un msg",8)
PrintLog.LCF_SetMsgLog(log.ERROR,"Je suis un msg sans data")
PrintLog.LCF_SortPerLevel("LogERROR.log",log.ERROR)"""


################################################################################
#		                    END OF FILE
################################################################################
##########################
# Function_name
##########################

######################################################
#
# @brief
# @details
#
#
#
#
# @params[in]
# @params[out]
# @retval
#
#####################################################






