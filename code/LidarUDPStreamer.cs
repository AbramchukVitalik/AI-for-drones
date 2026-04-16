using UnityEngine;
using System.Net.Sockets;
using System.Text;
using System;

public class LidarUDPStreamer : MonoBehaviour
{
    public string serverIP = "127.0.0.1";
    public int port = 6006;
    public int raysCount = 360;
    public float maxDistance = 20f;

    private UdpClient udpClient;

    void Start()
    {
        udpClient = new UdpClient();
    }

    void Update()
{
    float angleStep = 360f / raysCount;
    
    // Собираем пакет в JSON вручную для оптимизации
    StringBuilder sb = new StringBuilder();
    sb.Append("{");

    for (int i = 0; i < raysCount; i++)
    {
        float angle = i * angleStep;
        Vector3 direction = Quaternion.Euler(0, angle, 0) * transform.forward;
        float distance = maxDistance;

        if (Physics.Raycast(transform.position, direction, out RaycastHit hit, maxDistance))
        {
            distance = hit.distance;
        }

        sb.Append($"\"{Mathf.RoundToInt(angle)}\": {distance.ToString(System.Globalization.CultureInfo.InvariantCulture)}");
        if (i < raysCount - 1) sb.Append(",");
    }
    
    sb.Append("}");

    byte[] data = Encoding.UTF8.GetBytes(sb.ToString());
    
    try
    {
        // Отправляем все лучи одним UDP пакетом
        udpClient.Send(data, data.Length, serverIP, port);
    }
    catch (Exception e)
    {
        Debug.LogWarning($"[UDP] Send error: {e.Message}");
    }
}

    void OnApplicationQuit()
    {
        udpClient?.Close();
    }
}