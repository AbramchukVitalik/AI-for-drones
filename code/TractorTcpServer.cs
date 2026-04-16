using System;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;
using NWH.VehiclePhysics2;
using System.ComponentModel;

public class TractorTcpServer : MonoBehaviour
{
    [Header("TCP Server")]
    public int port = 9001;

    [Header("Controllers")]
    public VehicleController vehicle;
    public VehicleControlManager modeManager;
    public bool drivingBan = false;

    private TcpListener listener;
    private TcpClient client;
    private NetworkStream stream;
    private CancellationTokenSource cancelSource;

    private byte[] buffer = new byte[4096];

    private float targetSpeed = 0f;   // км/ч
    private float lastSteer = 0f;
    private bool flag = false;
    void Start()
    {
        if (vehicle == null)
            vehicle = GetComponent<VehicleController>();

        if (modeManager == null)
            modeManager = GetComponent<VehicleControlManager>();

        cancelSource = new CancellationTokenSource();
        StartServer();
    }

    void Update()
    {
        if (modeManager.mode != ControlMode.Manual || drivingBan)
            return;
        
        ApplySpeedControl();
    }

    private void ApplySpeedControl()
{
    float currentSpeed = vehicle.Speed * 3.6f; // м/с → км/ч
    float error = targetSpeed - currentSpeed;

    // --- STOP ---
    if (Mathf.Abs(targetSpeed) == 0f)
    {
        vehicle.input.Vertical = 0f;
        vehicle.input.Brakes = 1f;
        return;
    }

    // --- REVERSE ---
    if (targetSpeed < -0.01f)
    {
        if (currentSpeed > -Mathf.Abs(targetSpeed))
        {
            vehicle.input.Vertical = -0.4f;
            vehicle.input.Brakes = 0f;
        }
        else
        {
            vehicle.input.Vertical = -0.1f;
            vehicle.input.Brakes = 0f;
        }
        return;
    } 

    // --- FORWARD ---
    if (error > 0.2f)
    {
        vehicle.input.Vertical = Mathf.Clamp(error * 0.1f, 0.1f, 0.7f);
        vehicle.input.Brakes = 0f;
    }
    else if (error < -0.2f)
    {
        vehicle.input.Vertical = 0f;
        vehicle.input.Brakes = Mathf.Clamp(-error * 0.1f, 0f, 1f);
    }
    else
    {
        vehicle.input.Vertical = 0.1f;
        vehicle.input.Brakes = 0f;
    }
}

    void StartServer()
    {
        if (!flag)
        {
            listener = new TcpListener(IPAddress.Any, port);
            listener.Start();
            flag = true;
        }
        Debug.Log($"[TractorServer] Listening on port {port}");

        _ = AcceptLoop(cancelSource.Token);
    }

    private async Task AcceptLoop(CancellationToken token)
    {
        while (!token.IsCancellationRequested)
        {
            try
            {
                Debug.Log("[TractorServer] Waiting for client...");
                client = await listener.AcceptTcpClientAsync();

                Debug.Log("[TractorServer] Client connected!");

                stream = client.GetStream();
                _ = ReceiveLoop(token);
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"[TractorServer] Accept error: {ex.Message}");
            }
        }
    }

    private async Task ReceiveLoop(CancellationToken token)
    {
        var sb = new StringBuilder();

        while (!token.IsCancellationRequested && client.Connected)
        {
            try
            {
                int bytes = await stream.ReadAsync(buffer, 0, buffer.Length, token);
                if (bytes == 0)
                {
                    Debug.LogWarning("[TractorServer] Client disconnected.");
                    break;
                }

                string chunk = Encoding.UTF8.GetString(buffer, 0, bytes);
                sb.Append(chunk);

                int newline = sb.ToString().IndexOf('\n');
                while (newline >= 0)
                {
                    string line = sb.ToString().Substring(0, newline).Trim();
                    sb.Remove(0, newline + 1);

                    ProcessCommand(line);

                    newline = sb.ToString().IndexOf('\n');
                }
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"[TractorServer] Receive error: {ex.Message}");
                break;
            }
        }
    }

    private void ProcessCommand(string json)
    {
        if (string.IsNullOrWhiteSpace(json)) return;

        try
        {
            // --- режимы ---
            if (json.Contains("mode"))
            {
                ModeCommand mode = JsonUtility.FromJson<ModeCommand>(json);

                if (mode.mode == "manual")
                {
                    modeManager.SetMode(ControlMode.Manual);
                    Debug.Log("[TractorServer] MANUAL mode");
                }
                else if (mode.mode == "autopilot")
                {
                    modeManager.SetMode(ControlMode.Autopilot);
                    Debug.Log("[TractorServer] AUTOPILOT mode");
                }
                return;
            }
            // --- управление только в MANUAL ---
            if (modeManager.mode != ControlMode.Manual && !drivingBan)
                return;

            TractorCommand cmd = JsonUtility.FromJson<TractorCommand>(json);

            targetSpeed = cmd.targetSpeed;

            float s = Mathf.Clamp(cmd.steer, -1f, 1f);
            if (Mathf.Abs(s - lastSteer) > 0.0001f)
            {
                vehicle.input.Steering = s;
                lastSteer = s;
            }

            Debug.Log($"[TractorServer] Speed={cmd.targetSpeed}, Steer={cmd.steer}");
        }
        catch (Exception ex)
        {
            Debug.LogError($"[TractorServer] JSON error: {ex.Message}\n{json}");
        }
    }

    private void OnDestroy()
    {
        cancelSource?.Cancel();
        try { client?.Close(); listener?.Stop(); } catch { }
    }

    [Serializable]
    public class TractorCommand
    {
        public float targetSpeed;
        public float steer;
    }

    [Serializable]
    public class ModeCommand
    {
        public string mode;
    }
}
