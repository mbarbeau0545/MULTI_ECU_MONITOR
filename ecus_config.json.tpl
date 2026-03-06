{
  "general": {
    "mode": "SIL",
    "refresh_ms": 50,
    "can_broker": {
      "enabled": true,
      "poll_sleep_s": 0.001,
      "max_pop_per_ecu": 128,
      "max_inject_per_cycle": 2048,
      "control_port": 19600
    }
  },
  "ecus": [
    {
      "name": "ECU_GTRY",
      "enable_ecu": true,
      "ecu_in_debug": false,
      "sym_file": "Doc/ConfigPrj/GammaCfg/FirmwareOpeCfg/MessagingCfg/OpePrjMsgDefinition.sym",
      "project_software_cfg": "Doc/ConfigPrj/GammaCfg/FirmwareOpeCfg/Ope_Project_SoftwareCfg.xlsm",
      "fmkio_config_public": "D:/Project/Software/STM32/Gamma/Gamma_Firmware_AddHwCfg/src/1_FMK/FMK_CFG/FMKCFG_ConfigFiles/FMKIO_COnfigPublic.h",
      "encoder_modes": [
        {
          "idx": 0,
          "mode": "manual",
          "constant_speed": 0.0,
          "ramp_min": -1000.0,
          "ramp_max": 1000.0,
          "ramp_rate": 200.0,
          "sin_amp": 500.0,
          "sin_offset": 0.0,
          "sin_period_s": 4.0,
          "sig_pwm": 0,
          "sig_dir": 0,
          "pulses_per_revolution": 3200.0
        }
      ],
      "can_gate": "PCSIM",
      "can_speed_bps": 250000,
      "pcsim_can": {
        "timeout_s": 0.001,
        "poll_sleep_s": 5e-05,
        "max_pop_per_cycle": 128,
        "clear_can_tx_on_connect": true,
        "shared_can_nodes": [
          0,
          2,
          3,
          4
        ],
        "rx_filters": []
      },
      "udp": {
        "host": "127.0.0.1",
        "port": 19090,
        "timeout_s": 1.0,
        "node": 0
      }
    },
    {
      "name": "ECU_HC",
      "enable_ecu": true,
      "ecu_in_debug": false,
      "sym_file": "Doc/ConfigPrj/GammaCfg/FirmwareOpeCfg/MessagingCfg/OpePrjMsgDefinition.sym",
      "project_software_cfg": "Doc/ConfigPrj/GammaCfg/FirmwareOpeCfg/Ope_Project_SoftwareCfg.xlsm",
      "fmkio_config_public": "D:/Project/Software/STM32/Gamma/Gamma_Firmware_AddHwCfg/src/1_FMK/FMK_CFG/FMKCFG_ConfigFiles/FMKIO_COnfigPublic.h",
      "encoder_modes": [
        {
          "idx": 0,
          "mode": "manual",
          "constant_speed": 0.0,
          "ramp_min": -1000.0,
          "ramp_max": 1000.0,
          "ramp_rate": 200.0,
          "sin_amp": 500.0,
          "sin_offset": 0.0,
          "sin_period_s": 4.0,
          "sig_pwm": 0,
          "sig_dir": 0,
          "pulses_per_revolution": 3200.0
        }
      ],
      "can_gate": "PCSIM",
      "can_speed_bps": 250000,
      "udp": {
        "host": "127.0.0.1",
        "port": 19091,
        "timeout_s": 1.0,
        "node": 0
      },
      "pcsim_can": {
        "timeout_s": 0.001,
        "poll_sleep_s": 5e-05,
        "max_pop_per_cycle": 128,
        "clear_can_tx_on_connect": true,
        "shared_can_nodes": [
          0,
          2,
          3,
          4
        ],
        "rx_filters": []
      }
    },
    {
      "name": "ECU_MOT",
      "enable_ecu": true,
      "ecu_in_debug": false,
      "sym_file": "Doc/ConfigPrj/GammaCfg/FirmwareOpeCfg/MessagingCfg/OpePrjMsgDefinition.sym",
      "project_software_cfg": "Doc/ConfigPrj/GammaCfg/FirmwareOpeCfg/Ope_Project_SoftwareCfg.xlsm",
      "fmkio_config_public": "D:/Project/Software/STM32/Gamma/Gamma_Firmware_AddHwCfg/src/1_FMK/FMK_CFG/FMKCFG_ConfigFiles/FMKIO_COnfigPublic.h",
      "encoder_modes": [
        {
          "idx": 0,
          "mode": "manual",
          "constant_speed": 0.0,
          "ramp_min": -1000.0,
          "ramp_max": 1000.0,
          "ramp_rate": 200.0,
          "sin_amp": 500.0,
          "sin_offset": 0.0,
          "sin_period_s": 4.0,
          "sig_pwm": 0,
          "sig_dir": 0,
          "pulses_per_revolution": 3200.0
        }
      ],
      "can_gate": "PCSIM",
      "can_speed_bps": 250000,
      "udp": {
        "host": "127.0.0.1",
        "port": 19092,
        "timeout_s": 1.0,
        "node": 0
      },
      "pcsim_can": {
        "timeout_s": 0.001,
        "poll_sleep_s": 5e-05,
        "max_pop_per_cycle": 128,
        "clear_can_tx_on_connect": true,
        "shared_can_nodes": [
          0,
          2,
          3,
          4
        ],
        "rx_filters": []
      }
    },
    {
      "name": "ECU_SAFE",
      "enable_ecu": true,
      "ecu_in_debug": false,
      "sym_file": "Doc/ConfigPrj/GammaCfg/FirmwareSafetyCfg/MessagingCfg/SafetyPrjMsgDefinition.sym",
      "project_software_cfg": "Doc/ConfigPrj/GammaCfg/FirmwareSafetyCfg/Safety_Project_SoftwareCfg.xlsm",
      "fmkio_config_public": "D:/Project/Software/STM32/Gamma/Gamma_Safety_AddCfg/src/1_FMK/FMK_CFG/FMKCFG_ConfigFiles/FMKIO_COnfigPublic.h",
      "encoder_modes": [
        {
          "idx": 0,
          "mode": "manual",
          "constant_speed": 0.0,
          "ramp_min": -1000.0,
          "ramp_max": 1000.0,
          "ramp_rate": 200.0,
          "sin_amp": 500.0,
          "sin_offset": 0.0,
          "sin_period_s": 4.0,
          "sig_pwm": 0,
          "sig_dir": 0,
          "pulses_per_revolution": 3200.0
        }
      ],
      "can_gate": "PCSIM",
      "can_speed_bps": 250000,
      "udp": {
        "host": "127.0.0.1",
        "port": 19094,
        "timeout_s": 1.0,
        "node": 0
      },
      "pcsim_can": {
        "timeout_s": 0.001,
        "poll_sleep_s": 5e-05,
        "max_pop_per_cycle": 128,
        "clear_can_tx_on_connect": true,
        "shared_can_nodes": [
          0,
          2,
          3,
          4
        ],
        "rx_filters": []
      }
    }
  ]
}

