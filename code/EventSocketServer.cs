using System;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using UnityEngine;

public class EventSocketServer : MonoBehaviour
{
    [Header("Settings")]
    public int port = 7007;
    public VehicleControlManager controlManager;

    private TcpListener listener;
    private Thread serverThread;
    private bool running = true;

 

    void OnApplicationQuit()
    {
        running = false;
        listener?.Stop();
    }

    // Основной цикл сервера
 void Start()
{
    listener = new TcpListener(IPAddress.Any, port);
    listener.Start();
    serverThread = new Thread(ServerLoop);
    serverThread.IsBackground = true;
    serverThread.Start();
    Debug.Log($"[SERVER] Listening on port {port}");
}

void ServerLoop()
{
    while (running)
    {
        try
        {
            var client = listener.AcceptTcpClient();
            Debug.Log("[SERVER] Client connected");

            using (NetworkStream stream = client.GetStream())
            {
                byte[] buffer = new byte[1024];
                StringBuilder sb = new StringBuilder();

                while (running && client.Connected)
                {
                    int bytes = stream.Read(buffer, 0, buffer.Length);
                    if (bytes <= 0) break;

                    sb.Append(Encoding.UTF8.GetString(buffer, 0, bytes));

                    while (sb.ToString().Contains("\n"))
                    {
                        string full = sb.ToString();
                        int idx = full.IndexOf("\n");
                        string line = full.Substring(0, idx).Trim();
                        sb.Remove(0, idx + 1);

                        if (!string.IsNullOrEmpty(line))
                            HandleEvent(line);
                    }
                }
            }
        }
        catch (ObjectDisposedException)
        {
            Debug.Log("[SERVER] Listener stopped, exiting loop");
            break;
        }
        catch (Exception e)
        {
            Debug.LogWarning($"[SERVER] Error: {e.Message}");
            Thread.Sleep(500);
        }
    }
}


    
    void HandleEvent(string msg)
    {
       

        switch (msg.ToLower())
        {
            case "stop":
              
                controlManager.SetDrivingBan(true);

                break;
            case "go":
                 controlManager.SetDrivingBan(false);
                break;

            default:
                Debug.Log($"[EVENT] Unknown command: {msg}");
                break;
        }
    }
}
