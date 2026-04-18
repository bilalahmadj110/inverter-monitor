#!/bin/bash

# Inverter Monitoring Dashboard
# Displays PV power, load, battery status with auto-refresh

# Configuration
PORT="/dev/hidraw0"
PROTOCOL="PI30"
INTERVAL=3  # Update interval in seconds

# Function to clear previous lines
clear_lines() {
    for ((i=0; i<4; i++)); do
        printf "\033[1A\033[2K"  # Move up and clear line
    done
}

# Main loop
while true; do
    # Get data from inverter
    DATA=$(mpp-solar -p $PORT -P $PROTOCOL -c QPIGS -o json 2>/dev/null)
    
    # Extract values
    PV_POWER=$(echo "$DATA" | jq -r '.pv_input_power')
    LOAD_POWER=$(echo "$DATA" | jq -r '.ac_output_active_power')
    BAT_VOLT=$(echo "$DATA" | jq -r '.battery_voltage')
    BAT_CURRENT=$(echo "$DATA" | jq -r '.battery_charging_current')
    BAT_DISCHARGE=$(echo "$DATA" | jq -r '.battery_discharge_current')
    BAT_CAPACITY=$(echo "$DATA" | jq -r '.battery_capacity')
    
    # Calculate battery power flow
    if (( $(echo "$BAT_CURRENT > 0" | bc -l) )); then
        BAT_POWER=$(echo "$BAT_CURRENT * $BAT_VOLT" | bc)
        BAT_STATUS="Charging: ${BAT_POWER%.*}W"
    elif (( $(echo "$BAT_DISCHARGE > 0" | bc -l) )); then
        BAT_POWER=$(echo "$BAT_DISCHARGE * $BAT_VOLT" | bc)
        BAT_STATUS="Discharging: ${BAT_POWER%.*}W"
    else
        BAT_STATUS="Idle"
    fi
    
    # Clear previous output
    clear_lines
    
    # Display current values
    echo "┌────────────────────────────────────────────────────┐"
    echo "│ Inverter Monitoring Dashboard (Update every $INTERVAL sec) │"
    echo "├────────────────────────────────────────────────────┤"
    printf "│ PV Power: %-5dW │ Load: %-5dW │ Battery: %-3d%% │\n" $PV_POWER $LOAD_POWER $BAT_CAPACITY
    echo "│                                                    │"
    printf "│ Battery Status: %-30s │\n" "$BAT_STATUS"
    echo "└────────────────────────────────────────────────────┘"
    
    # Wait before next update
    sleep $INTERVAL
done
