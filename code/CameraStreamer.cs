using System.Net.Sockets;
using UnityEngine;

public class CameraStreamer : MonoBehaviour
{
    [Header("UDP Settings")]
    public string remoteIP = "127.0.0.1";
    public int remotePort = 5005;

    [Header("Camera Settings")]
    public Camera cam;
    public int imageWidth = 640;
    public int imageHeight = 480;

    private UdpClient client;
    private Texture2D tex;
    private byte[] buffer;

    void Start()
    {
        client = new UdpClient();
        client.Connect(remoteIP, remotePort);

        if (cam == null)
            cam = Camera.main;

        tex = new Texture2D(imageWidth, imageHeight, TextureFormat.RGB24, false);
        buffer = new byte[imageWidth * imageHeight * 3];
    }

    void LateUpdate()
    {
        SendCameraFrame();
    }

    void SendCameraFrame()
    {
        RenderTexture rt = new RenderTexture(imageWidth, imageHeight, 24);
        cam.targetTexture = rt;
        cam.Render();

        RenderTexture.active = rt;
        tex.ReadPixels(new Rect(0, 0, imageWidth, imageHeight), 0, 0);
        tex.Apply();

        cam.targetTexture = null;
        RenderTexture.active = null;
        Destroy(rt);

        // RAW RGB24
        buffer = tex.GetRawTextureData();

        // UDP send
        client.Send(buffer, buffer.Length);
    }

    void OnApplicationQuit()
    {
        client?.Close();
    }
}
