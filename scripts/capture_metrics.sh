#!/bin/bash
LOGFILE="/opt/klinik/data/gpu_metrics.csv"

echo "timestamp,gpu_util,mem_used_mb,mem_total_mb,temp_c,power_w" > $LOGFILE

while true; do
  TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  DATA=$(rocm-smi --showuse --showmemuse --showtemp --showpower --csv 2>/dev/null | tail -1)
  echo "$TS,$DATA" >> $LOGFILE
  sleep 5
done
