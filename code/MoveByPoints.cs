using UnityEngine;

public class MoveByPoints : MonoBehaviour
{
    public Transform[] waypoints;      // Точки маршрута
    public float speed = 3f;           // Скорость движения
    public float reachDistance = 0.2f; // Радиус достижения точки

    public enum Mode { Loop, PingPong, OneWay }
    public Mode mode = Mode.Loop;

    private int index = 0;
    private int direction = 1; // Для PingPong

    void Update()
    {
        if (waypoints.Length == 0) return;

        Transform target = waypoints[index];
        Vector3 dir = (target.position - transform.position).normalized;

        transform.position += dir * speed * Time.deltaTime;

        // Поворот в сторону движения
        if (dir != Vector3.zero)
            transform.rotation = Quaternion.Lerp(
                transform.rotation,
                Quaternion.LookRotation(dir),
                Time.deltaTime * 5f
            );

        // Проверяем достижение точки
        if (Vector3.Distance(transform.position, target.position) < reachDistance)
            AdvanceIndex();
    }

    void AdvanceIndex()
    {
        switch (mode)
        {
            case Mode.Loop:
                index = (index + 1) % waypoints.Length;
                break;

            case Mode.OneWay:
                if (index < waypoints.Length - 1)
                    index++;
                break;

            case Mode.PingPong:
                if (index == waypoints.Length - 1) direction = -1;
                else if (index == 0) direction = 1;

                index += direction;
                break;
        }
    }
}
