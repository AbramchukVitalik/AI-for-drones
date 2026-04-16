using System;
using System.Net.Sockets;
using UnityEngine;

public class TCPStreamer : MonoBehaviour
{
    public string remoteIP = "127.0.0.1";
    public int remotePort = 5005;

    public Camera cam;
    public int imageWidth = 640;
    public int imageHeight = 480;
    public int jpegQuality = 70;

    private TcpClient client;
    private NetworkStream stream;
    private Texture2D tex;

    void Start()
    {
        client = new TcpClient();
        client.Connect(remoteIP, remotePort);
        stream = client.GetStream();

        if (cam == null)
            cam = Camera.main;

        tex = new Texture2D(imageWidth, imageHeight, TextureFormat.RGB24, false);
    }

    void LateUpdate()
    {
        SendCameraFrame();
    }

    void SendCameraFrame()
    {
        // Render camera
        RenderTexture rt = new RenderTexture(imageWidth, imageHeight, 24);
        cam.targetTexture = rt;
        cam.Render();

        RenderTexture.active = rt;
        tex.ReadPixels(new Rect(0, 0, imageWidth, imageHeight), 0, 0);
        tex.Apply();

        cam.targetTexture = null;
        RenderTexture.active = null;
        Destroy(rt);

        // Encode to JPEG
        byte[] jpg = tex.EncodeToJPG(jpegQuality);

        // Send length (4 bytes)
        byte[] lengthBytes = BitConverter.GetBytes(jpg.Length);
        stream.Write(lengthBytes, 0, 4);

        // Send JPEG data
        stream.Write(jpg, 0, jpg.Length);
    }

    void OnApplicationQuit()
    {
        stream?.Close();
        client?.Close();
    }
}
