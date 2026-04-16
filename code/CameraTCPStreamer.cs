using System.Net.Sockets;
using UnityEngine;

public class CameraTCPStreamer : MonoBehaviour
{
    public string serverIp = "127.0.0.1"; 
    public int serverPort = 5005;

    public int width = 640;
    public int height = 480;
    public int sendFps = 20;

    private Camera cam;
    private RenderTexture rt;
    private Texture2D tex;
    private TcpClient client;
    private NetworkStream stream;
    private float interval;
    private float timer;

    void Start()
    {
        Application.runInBackground = true;

        cam = GetComponent<Camera>();
        rt = new RenderTexture(width, height, 16);
        cam.targetTexture = rt;

        tex = new Texture2D(width, height, TextureFormat.RGB24, false);

        client = new TcpClient();
        client.Connect(serverIp, serverPort);
        stream = client.GetStream();

        interval = 1f / sendFps;
    }

    void OnDestroy()
    {
        stream?.Close();
        client?.Close();
        cam.targetTexture = null;
        rt?.Release();
    }

    void LateUpdate()
    {
        timer += Time.deltaTime;
        if (timer < interval) return;
        timer = 0f;

        SendFrame();
    }

    void SendFrame()
    {
        RenderTexture.active = rt;
        tex.ReadPixels(new Rect(0, 0, width, height), 0, 0);
        tex.Apply(false);
        RenderTexture.active = null;

        byte[] data = tex.GetRawTextureData();
        int size = data.Length;

        byte[] header = System.BitConverter.GetBytes(size);
        if (System.BitConverter.IsLittleEndian)
            System.Array.Reverse(header);

        stream.Write(header, 0, 4);
        stream.Write(data, 0, size);
    }
}
