PROGRAM tank_ctrl
VAR_INPUT
  start   : BOOL := FALSE;   (* momentary run/restart pushbutton *)
  estop   : BOOL := FALSE;   (* TRUE = emergency stop pressed *)
  high_ls : BOOL := FALSE;   (* high level switch, TRUE = tank full *)
  low_ls  : BOOL := FALSE;   (* low level switch, TRUE = tank dry *)
  level   : REAL := 0.0;     (* analog level transmitter, cm *)
END_VAR
VAR_OUTPUT
  pump         : BOOL := FALSE;  (* main drain pump *)
  inlet_valve  : BOOL := FALSE;  (* fill valve *)
  outlet_valve : BOOL := FALSE;  (* discharge valve in series with pump *)
  alarm        : BOOL := FALSE;  (* latched fault indication *)
  running      : BOOL := FALSE;  (* latched run-mode indicator *)
END_VAR
VAR
  start_prev : BOOL := FALSE;  (* previous scan value of start *)
  stop_latch : BOOL := FALSE;  (* set by E-stop, cleared by start *)
  fault_latch: BOOL := FALSE;  (* set on sensor discrepancy *)
  mode_fill  : BOOL := TRUE;   (* TRUE = filling, FALSE = draining *)
END_VAR

  (* ---- rising edge of start resets latches and engages run mode ---- *)
  IF start AND NOT start_prev THEN
    stop_latch  := FALSE;
    fault_latch := FALSE;
    alarm       := FALSE;
    running     := TRUE;
  END_IF;
  start_prev := start;

  (* ---- emergency stop: latched; released button does not restart ---- *)
  IF estop THEN
    stop_latch := TRUE;
  END_IF;

  IF stop_latch OR fault_latch THEN
    (* fail-safe hold: nothing may actuate until a fresh start *)
    pump         := FALSE;
    inlet_valve  := FALSE;
    outlet_valve := FALSE;
    running      := FALSE;
    alarm        := TRUE;
  ELSIF NOT running THEN
    (* idle: not started *)
    pump         := FALSE;
    inlet_valve  := FALSE;
    outlet_valve := FALSE;
    alarm        := FALSE;
  ELSE
    (* ---- normal automatic fill / drain cycle ---- *)

    (* band switching, driven by the discrete level switches *)
    IF high_ls THEN
      mode_fill := FALSE;   (* tank full enough: stop filling *)
    END_IF;
    IF low_ls THEN
      mode_fill := TRUE;    (* tank dry: start filling *)
    END_IF;

    IF mode_fill THEN
      inlet_valve  := TRUE;
      pump         := FALSE;
      outlet_valve := FALSE;
    ELSE
      inlet_valve  := FALSE;
      IF level > 15.0 AND NOT low_ls THEN
        pump         := TRUE;
        outlet_valve := TRUE;
      ELSE
        pump         := FALSE;
        outlet_valve := FALSE;
      END_IF;
    END_IF;

    (* ---- independent analog safety interlocks ---- *)
    IF level > 88.0 THEN
      inlet_valve := FALSE;   (* overflow guard: hard cap even if switch lies *)
    END_IF;
    IF level < 15.0 OR low_ls THEN
      pump         := FALSE;  (* dry-run interlock: never run below low switch *)
      outlet_valve := FALSE;
    END_IF;

    (* ---- sensor discrepancy detection (high switch vs analog) ---- *)
    IF (high_ls AND level < 75.0) OR
       (low_ls AND level > 30.0) OR (NOT low_ls AND level < 8.0) THEN
      fault_latch := TRUE;
    END_IF;
  END_IF;

  (* a latched fault forces the safe state even if the branch above ran *)
  IF fault_latch THEN
    pump         := FALSE;
    inlet_valve  := FALSE;
    outlet_valve := FALSE;
    running      := FALSE;
    alarm        := TRUE;
  END_IF;
END_PROGRAM

CONFIGURATION tank_cfg
  TASK fast(INTERVAL := T#10ms, PRIORITY := 0);
  PROGRAM p1 WITH fast : tank_ctrl;
END_CONFIGURATION