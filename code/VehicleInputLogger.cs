using UnityEngine;
using NWH.VehiclePhysics2;

public class VehicleInputLogger : MonoBehaviour
{
    public VehicleController vehicle;

    private float lastSteer;
    private float lastThrottle;
    private float lastBrake;
    private float lastHandbrake;

    void Awake()
    {
        if (vehicle == null)
            vehicle = GetComponent<VehicleController>();

        Debug.Log("<color=cyan>[LOGGER]</color> Logger initialized.");
    }

    void Update()
    {
        LogChanges("Update()");
    }

    void FixedUpdate()
    {
        LogChanges("FixedUpdate()");
    }

    void LateUpdate()
    {
        LogChanges("LateUpdate()");
    }

    private void LogChanges(string source)
    {
        if (vehicle == null) return;

        var input = vehicle.input;

        if (Mathf.Abs(input.Steering - lastSteer) > 0.0001f)
        {
            Debug.Log($"<color=yellow>[STEER CHANGE]</color> {source}  {lastSteer:F3} → {input.Steering:F3}");
            lastSteer = input.Steering;
        }

        if (Mathf.Abs(input.Vertical - lastThrottle) > 0.0001f)
        {
            Debug.Log($"<color=green>[THROTTLE CHANGE]</color> {source}  {lastThrottle:F3} → {input.Vertical:F3}");
            lastThrottle = input.Vertical;
        }

        if (Mathf.Abs(input.Brakes - lastBrake) > 0.0001f)
        {
            Debug.Log($"<color=red>[BRAKE CHANGE]</color> {source}  {lastBrake:F3} → {input.Brakes:F3}");
            lastBrake = input.Brakes;
        }

        if (Mathf.Abs(input.Handbrake - lastHandbrake) > 0.0001f)
        {
            Debug.Log($"<color=magenta>[HANDBRAKE CHANGE]</color> {source}  {lastHandbrake:F3} → {input.Handbrake:F3}");
            lastHandbrake = input.Handbrake;
        }
    }
}

