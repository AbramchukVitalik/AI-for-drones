using System.Collections.Generic;
using UnityEngine;

public class PathCollector : MonoBehaviour
{
    [Header("Контейнер точек пути")]
    public Transform pathContainer;

    [Header("Список точек")]
    public List<Transform> waypoints = new List<Transform>();

    [Header("Настройки Gizmos")]
    public Color lineColor = Color.green;
    public Color pointColor = Color.yellow;
    public Color targetColor = Color.red;
    public float waypointGizmoSize = 0.3f;
    public int currentPointIndex = 0;

    void Awake()
    {
        RefreshWaypoints();
    }

    void OnValidate()
    {
        RefreshWaypoints();
    }

    public void RefreshWaypoints()
    {
        waypoints.Clear();

        if (pathContainer == null) return;

        foreach (Transform child in pathContainer.transform)
        {
            waypoints.Add(child);
        }
    }

    private void OnDrawGizmos()
    {
        if (pathContainer == null) return;
        if (waypoints.Count == 0) RefreshWaypoints();

        // --- Линии ---
        Gizmos.color = lineColor;
        for (int i = 0; i < waypoints.Count - 1; i++)
        {
            Gizmos.DrawLine(waypoints[i].position, waypoints[i + 1].position);
        }

        // --- Точки ---
        Gizmos.color = pointColor;
        foreach (Transform wp in waypoints)
        {
            Gizmos.DrawSphere(wp.position, waypointGizmoSize);
        }

        // --- Целевая точка ---
        if (currentPointIndex < waypoints.Count)
        {
            Gizmos.color = targetColor;
            Gizmos.DrawSphere(waypoints[currentPointIndex].position, waypointGizmoSize * 1.3f);
        }
    }
}
