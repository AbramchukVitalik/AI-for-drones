using System.Net.Sockets;
using System.Text;
using UnityEngine;

public class LidarTcpStreamer : MonoBehaviour
{
    public string serverIp = "127.0.0.1";
    public int serverPort = 6006;

    public int startAngle = 0;
    public int endAngle = 359;
    public float scanHz = 20f;

    public bool drawRays = true;
    public float rayLengthMultiplier = 1f;

    public float maxDistance = 100f;
    public float noiseAmplitude = 0.02f;

    public LayerMask layerMask = -1;

    private TcpClient client;
    private NetworkStream stream;
    private float interval;
    private float timer;

    public float[] lidarDistances = new float[360];

    private Collider[] selfColliders;

    void Start()
    {
        Application.runInBackground = true;

        // Собираем ВСЕ свои коллайдеры
        selfColliders = GetComponentsInChildren<Collider>();

        // Если маска не задана — включаем все слои
        if (layerMask == -1)
        {
            layerMask = Physics.DefaultRaycastLayers;
        }

        try
        {
            client = new TcpClient();
            client.Connect(serverIp, serverPort);
            stream = client.GetStream();
            interval = 1f / scanHz;
            Debug.Log($"LIDAR подключен к {serverIp}:{serverPort}");
        }
        catch (System.Exception e)
        {
            Debug.LogWarning($"LIDAR работает локально: {e.Message}");
        }
    }

    void OnDestroy()
    {
        stream?.Close();
        client?.Close();
    }

    void Update()
    {
        timer += Time.deltaTime;

        DrawRays();

        if (timer < interval)
            return;

        timer = 0f;

        PerformLocalScan();

        if (stream != null && client.Connected)
        {
            SendFullScan();
        }
    }

    // -----------------------------
    // ЛОКАЛЬНОЕ СКАНИРОВАНИЕ
    // -----------------------------
    void PerformLocalScan()
    {
        for (int angle = startAngle; angle <= endAngle; angle++)
        {
            Quaternion rot = Quaternion.Euler(0, angle, 0);
            Vector3 dir = rot * Vector3.forward;

            // Смещаем начало луча, чтобы не стартовать изнутри коллайдера
            Vector3 origin = transform.position + dir * 0.05f;

            float dist = maxDistance;

            if (Physics.Raycast(origin, dir, out RaycastHit hit, maxDistance, layerMask, QueryTriggerInteraction.Ignore))
            {
                // Игнорируем попадание в собственный объект
                if (IsSelfCollider(hit.collider))
                {
                    lidarDistances[angle] = maxDistance;
                    continue;
                }

                dist = hit.distance;

                // Добавляем шум
                float noise = Random.Range(-noiseAmplitude, noiseAmplitude);
                dist *= (1 + noise);

                dist = Mathf.Clamp(dist, 0.01f, maxDistance);
            }

            lidarDistances[angle] = dist;
        }
    }

    // Проверка: попали ли в свой объект
    bool IsSelfCollider(Collider col)
    {
        foreach (var c in selfColliders)
        {
            if (col == c)
                return true;
        }
        return false;
    }

    // -----------------------------
    // ОТПРАВКА ДАННЫХ
    // -----------------------------
    void SendFullScan()
    {
        if (stream == null) return;

        try
        {
            StringBuilder sb = new StringBuilder();

            for (int angle = startAngle; angle <= endAngle; angle++)
            {
                sb.AppendFormat(System.Globalization.CultureInfo.InvariantCulture,
                    "{0},{1:F3}\n", angle, lidarDistances[angle]);
            }

            byte[] data = Encoding.ASCII.GetBytes(sb.ToString());
            stream.Write(data, 0, data.Length);
        }
        catch
        {
            TryReconnect();
        }
    }

    void TryReconnect()
    {
        try
        {
            stream?.Close();
            client?.Close();

            client = new TcpClient();
            client.Connect(serverIp, serverPort);
            stream = client.GetStream();
            Debug.Log("LIDAR переподключен");
        }
        catch
        {
            Debug.LogWarning("LIDAR: переподключение не удалось");
        }
    }

    // -----------------------------
    // ОТРИСОВКА ЛУЧЕЙ
    // -----------------------------
    void DrawRays()
    {
        if (!drawRays) return;

        for (int angle = startAngle; angle <= endAngle; angle++)
        {
            float dist = lidarDistances[angle];
            Quaternion rot = Quaternion.Euler(0, angle, 0);
            Vector3 dir = rot * Vector3.forward;

            Color c = Color.Lerp(Color.green, Color.red, dist / maxDistance);
            if (Mathf.Approximately(dist, maxDistance))
                c = Color.cyan;

            Debug.DrawLine(
                transform.position,
                transform.position + dir * dist * rayLengthMultiplier,
                c,
                Time.deltaTime,
                false
            );
        }
    }

    // -----------------------------
    // API ДЛЯ АВТОПИЛОТА
    // -----------------------------
    public float[] GetSector(int centerAngle, int halfWidth)
    {
        int size = halfWidth * 2 + 1;
        float[] result = new float[size];

        for (int i = -halfWidth; i <= halfWidth; i++)
        {
            int angle = (centerAngle + i + 360) % 360;
            result[i + halfWidth] = lidarDistances[angle];
        }

        return result;
    }

    public float GetDistanceAtAngle(int angle)
    {
        angle = (angle + 360) % 360;
        return lidarDistances[angle];
    }

    public bool HasObstacle(int angle, float thresholdDistance)
    {
        return GetDistanceAtAngle(angle) < thresholdDistance;
    }
}
