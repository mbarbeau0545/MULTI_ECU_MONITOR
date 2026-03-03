# MULTI_ECU_MONITOR

Monitor SIL/HIL multi-ECU avec IHM SignalViewer + I/O PCSIM.

## Architecture CAN centralisee (nouveau)

Le mode SIL peut maintenant lancer un **broker CAN central** qui connecte tous les `program.exe` PCSIM.

- Chaque ECU continue d'avoir son endpoint UDP PCSIM (`udp.host/port`).
- Le broker lit les trames TX de chaque ECU via une **file dediee broker** (`POP_CAN_BROKER_TX_BURST`).
- Le broker route par `node` CAN (ex: 0,2,3,4) et par abonnement RX:
  - filtres statiques JSON (`pcsim_can.rx_filters`), ou
  - abonnements reels de l'exe (`DUMP_CAN_RX_REG_BURST`) si aucun filtre statique.
- Le broker injecte ensuite la trame vers les ECU abonnes (`INJECT_CAN_EX`).

Important: la file `POP_CAN_TX_BURST` historique est conservee pour les viewers/IHM et n'est plus consommee par le broker.

## Configuration JSON

Fichier: `Doc/ConfigPrj/ecus_config.json`

### General

```json
"general": {
  "mode": "SIL",
  "refresh_ms": 50,
  "can_broker": {
    "enabled": true,
    "control_port": 19600,
    "poll_sleep_s": 0.001,
    "max_pop_per_ecu": 128,
    "max_inject_per_cycle": 2048
  }
}
```

### Par ECU (PCSIM)

Sous `pcsim_can`:

- `shared_can_nodes`: liste des index CAN partages (ex `[0,2,3,4]`)
- `rx_filters`: filtres optionnels `[{"node":0,"id":"0x18FF0130","mask":"0x1FFFFFFF","extended":true}]`

Si `rx_filters` est vide, le broker utilise les abonnements RX reels exposes par l'exe.

## Lancement

- Multi monitor: `python tools/MultiEcuMonitor/multi_ecu_monitor.py --config Doc/ConfigPrj/ecus_config.json`
- Broker seul (sans IHM): `python tools/MultiEcuMonitor/can_broker.py --config Doc/ConfigPrj/ecus_config.json`
- Lancement ECU via `.bat`: `Doc/ConfigPrj/launch_multi_exe.bat`
  - Le script ping `127.0.0.1:<general.can_broker.control_port>`.
  - Si broker deja present: il ne relance pas un second broker.
  - Si absent: il demarre `tools/MultiEcuMonitor/can_broker.py` puis lance les ECU.

## Notes runtime

- La barre de statut affiche l'etat broker: `rx`, `routed`, `injected`, `dropped`, `cycle`, `err`.
- Le broker ne s'active que si `general.can_broker.enabled=true` et au moins 2 ECU PCSIM actifs.
- Si le monitor est demarre apres le `.bat`, il detecte le broker externe et ne cree pas de doublon.
