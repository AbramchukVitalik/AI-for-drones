using UnityEngine;
using NWH.VehiclePhysics2;



public class TractorTestControl : MonoBehaviour
{
    public VehicleController vehicle;

    public float holdTime = 2f; // сколько держать руль в одну сторону
    private float timer = 0f;
    private bool steeringRight = true;

    void Start()
    {
        if (vehicle == null)
            vehicle = GetComponent<VehicleController>();

        vehicle.input.autoSetInput = false;
    }

    void Update()
    {
        timer += Time.deltaTime;

        // --- ПЕРЕКЛЮЧЕНИЕ НАПРАВЛЕНИЯ ---
        if (timer >= holdTime)
        {
            steeringRight = !steeringRight;
            timer = 0f;
        }

        // --- УГОЛ ПОВОРОТА ---
        float steerNorm = steeringRight ? 1f : -1f; // нормализованный [-1..1]
        float steerRad = steerNorm * UnityBridge.Instance.maxSteerRad;

        // --- ПОВОРОТ ЧЕРЕЗ UNITYBRIDGE ---
        UnityBridge.SendSteerAngle(steerRad);

        // --- ВИЗУАЛЬНЫЙ РУЛЬ ---
        double wheelAngle = steerNorm * 540.0;
        SteeringWheelController.Instance?.SetSteeringAngle(wheelAngle);

        // --- ГАЗ ---
        vehicle.input.Vertical = 1f;
        vehicle.input.Brakes = 0f;
        vehicle.input.Handbrake = 0f;
    }
}
