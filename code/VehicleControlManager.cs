using UnityEngine;
using NWH.VehiclePhysics2;
using System.Diagnostics;


public class VehicleControlManager : MonoBehaviour
{
    public VehicleController vehicle;
    public TractorAutopilot autopilot;
    public TractorTcpServer driving;
    public bool drivingBan = false;
    public ControlMode mode = ControlMode.Manual;

    void Start()
    {
        SetDrivingBan(drivingBan);
        mode = ControlMode.Autopilot;
    }
    void Awake()
    {
        if (vehicle == null)
            vehicle = GetComponent<VehicleController>();
        vehicle.input.autoSetInput = false;
        SetDrivingBan(drivingBan);
        ApplyMode(mode);
    }

    public void SetMode(ControlMode newMode)
    {
        if (mode == newMode) return;
        mode = newMode;

        ApplyMode(mode);
       
    }

    private void ApplyMode(ControlMode m)
    {
        Reset();
        switch (m)
        {
            case ControlMode.Manual:
                SetManualMode();
                break;
            case ControlMode.Autopilot:
                SetAutopilotMode();
                break;
        }
    }
      private void StopTractor()
    {
        vehicle.input.Vertical = 0f;
        vehicle.input.Brakes = 1f;
        vehicle.input.Steering = 0f;
    }
    public void SetDrivingBan(bool ban)
    {
        autopilot.drivingBan = ban;
        driving.drivingBan = ban;
        drivingBan = ban;
        if (ban)
        {
            StopTractor();
            vehicle.input.Handbrake = 1f; 
        }
        else
        {
            vehicle.input.Handbrake = 0f; 
        }
    }
    private void Reset()
    {
        vehicle.input.Vertical = 0;
        vehicle.input.Brakes = 0;
        vehicle.input.Handbrake = 0;
    }
    private void SetManualMode()
    {
        if (autopilot != null) {
            autopilot.ToggleAutopilot(false);
        }
    }

    private void SetAutopilotMode()
    {
        if (autopilot != null) autopilot.ToggleAutopilot(true);
    }
}

