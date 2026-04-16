using System.Net;
using System.Net.Sockets;
using System.Text;
using UnityEngine;

public class LiDAR3D : MonoBehaviour
{
    [Header("UDP Settings")]
    public string remoteIP = "127.0.0.1";
    public int remotePort = 6006;

    [Header("LiDAR Settings")]
    public float maxDistance = 50f;
    public int startAngle = 0;
    public int endAngle = 360;
    public int angleStep = 1;
    public float scanInterval = 0.05f;

    private UdpClient udpClient;
    private IPEndPoint remoteEndPoint;
    private float timer;

    void Start()
    {
        udpClient = new UdpClient();
        remoteEndPoint = new IPEndPoint(IPAddress.Parse(remoteIP), remotePort);
    }

    void Update()
    {
        timer += Time.deltaTime;
        if (timer >= scanInterval)
        {
            timer = 0f;
            SendLidarScan();
        }
    }

    void SendLidarScan()
    {
        Vector3 origin = transform.position;
        Quaternion baseRotation = transform.rotation;

        for (int angle = startAngle; angle < endAngle; angle += angleStep)
        {
            Quaternion rot = baseRotation * Quaternion.Euler(0f, angle, 0f);
            Vector3 dir = rot * Vector3.forward;

            float distanceMeters = maxDistance;

            if (Physics.Raycast(origin, dir, out RaycastHit hit, maxDistance))
                distanceMeters = hit.distance;

            // Python expects meters, not mm
            string msg = $"{angle},{distanceMeters:F2}";
            byte[] data = Encoding.ASCII.GetBytes(msg);

            udpClient.Send(data, data.Length, remoteEndPoint);

            Debug.DrawRay(origin, dir * distanceMeters, Color.green, scanInterval);
        }
    }

    void OnApplicationQuit()
    {
        udpClient?.Close();
    }
}
