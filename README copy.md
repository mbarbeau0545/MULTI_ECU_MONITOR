# Multi ECU Monitor

Architecture modulaire dans `tools/multi_ecu_monitor/app`.

## But

- 1 fichier JSON d'entrée avec N ECU
- 1 onglet principal par ECU
- Utilisation de `CANMngmt.py` (via `FrameMngmt` / `IhmSigViewer`) pour toute la couche CAN dans les onglets SignalViewer.

## Mode Global

Dans `ecus_config.json`:

- `general.mode = "SIL"`:
  - onglet `I/O` actif (pilotage direct `program.exe` via PC_SIM UDP)
  - onglet `SignalViewer` actif
- `general.mode = "HIL"`:
  - pas d'onglet `I/O`
  - uniquement onglet `SignalViewer` (Messages, MessageSender, Sensors, Actuators, Graph...)

## Structure

- `app/config.py`: parsing config globale + ECU
- `app/fmkio_parser.py`: lecture comptes I/O depuis `FMKIO_ConfigPublic.h`
- `app/sil_io_tab.py`: onglet I/O SIL
- `app/signalviewer_embed.py`: intégration widget `IhmSigViewer.SignalViewer` par ECU
- `app/ecu_page.py`: composition des sous-onglets ECU
- `app/main_window.py`: fenêtre principale
- `app/launcher.py`: point d'entrée applicatif
- `multi_ecu_monitor.py`: launcher mince

## Config JSON

Exemple minimal:

```json
{
  "general": {
    "mode": "SIL",
    "refresh_ms": 200
  },
  "ecus": [
    {
      "name": "ECU_1",
      "sym_file": "../../Doc/.../SafetyPrjMsgDefinition.sym",
      "project_software_cfg": "../../Src/Config/project_cfg_ecn1.json",
      "fmkio_config_public": "../../src/1_FMK/.../FMKIO_COnfigPublic.h",
      "can_gate": "PCSIM",
      "can_speed_bps": 500000,
      "udp": {
        "host": "127.0.0.1",
        "port": 19090,
        "timeout_s": 0.4,
        "node": 0
      }
    }
  ]
}
```

Notes:

- `project_software_cfg` peut être un JSON de projet SignalViewer existant.
- Si `can_gate = PCSIM`, le bridge CAN utilise `udp.host/port/node`.
- Si `can_gate != PCSIM`, définir `can_device_port` dans l'ECU.

## Lancement

```bash
pip install PyQt5 pyqtgraph
python tools/multi_ecu_monitor/multi_ecu_monitor.py --config tools/multi_ecu_monitor/ecus_config.json
```

## Validation config

Au démarrage, un validateur vérifie:

- existence des chemins (`sym_file`, `project_software_cfg`, `fmkio_config_public`)
- mode global (`SIL`/`HIL`)
- `can_gate` autorisé (`PCSIM`, `PEAK`, `WAVESHARE`)
- paramètres UDP (`host`, `port`, `timeout_s`, `node`)
- doublons de endpoints UDP PCSIM (`host:port`)

En cas d'erreur, l'application s'arrête avec un message détaillé.
