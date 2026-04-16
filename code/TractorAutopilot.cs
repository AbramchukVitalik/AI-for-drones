using UnityEngine;
using System.Collections.Generic;
using NWH.VehiclePhysics2;
using TMPro;
using System;
using UnityEditor;
using System.IO.MemoryMappedFiles;
public class TractorAutopilot : MonoBehaviour
{
	[Header("Autopilot")]
	public bool isAutoMode = false;
    [Header("Vehicle")]
    public VehicleController vehicle;
    [Header("Detour")]
	public LidarTcpStreamer lidar;
    public PathCollector collector;
	public int sector;

    [Header("Path")]
    public GameObject pathContainer;
    public List<Transform> waypoints = new List<Transform>();
    public float arrivalDistance = 4.0f;

    [Header("Speed Control")]
    public float maxRouteSpeed = 10f; // km/h
    public float accelRate = 2f;
    public float brakeRate = 3f;
    public float slowTurnSpeed = 4f;
	public float slowDownDistance = 50f;  
	public float wheelInfluence = 0.5f; 
	public TextMeshProUGUI Speedometr;
	public Rigidbody tractorRb;
    public bool drivingBan= false;

    [Header("Steering Control")]
    public float steeringSmoothing = 4f;
    public float maxSteerAngle = 45f;
    public float turnToLine = 0.5f;
    public float deviationLimit = 30f;
    public float permissibleLimit = 1f;
    public float minimumSpeedAngle = 90f;
	public float distanceToDetour = 5;
    public float influenceOfLet = 0.7f;
    public float detourLength = 10f;
    public float turnRadius = 0.2f;
    public float distanceFromAngle = 3.0f;
    public float critical_dist = 2.0f;
    public int strength_sector = 20;
    public float strength_turn = 0.2f;
    public float turning_shape = 1f;
    public float reverse = 2f;

    private bool critical_stop = false;


    private bool IsDetour = false;
    private int currentPointIndex = 0;
	private float signedSpeed = 0f;
	private float displaySpeed = 0f;
    private Vector3 turnStartPosition;
    private LineRenderer lineRenderer;
    private Vector3 reverseStartPosition = Vector3.negativeInfinity;
    void Start()
    {
        reverseStartPosition = Vector3.negativeInfinity;
    }
    void Awake()
    {
        reverseStartPosition = Vector3.negativeInfinity;
        if (vehicle == null)
            vehicle = GetComponent<VehicleController>();

        vehicle.input.autoSetInput = false;
        LoadWaypoints();
    }

    void LoadWaypoints()
    {
        waypoints.Clear();
        foreach (Transform child in pathContainer.transform)
            waypoints.Add(child);
    }

    void Update()
    {
        if (isAutoMode)
        {
            if (critical_stop && !drivingBan)
            {
                Reverse();
            }
            else if (!drivingBan)
            {  
                DriveToWaypoint();
            }
            else
            {
                StopTractor();
            } 
        }
		UpdateStatus();
    }
    int e = 0;
    private void Reverse()
    {
        Debug.Log("[Reverse = x]");
        if(e < 10)
        {
            StopTractor();
            ++e;
        }
        else if(e < 20)
        {
            ReleaseEmergencyStop();
            ++e;
        }
        else if(reverseStartPosition.Equals(Vector3.negativeInfinity))
		{
			reverseStartPosition = transform.position;
		}
		else if (Vector3.Distance(reverseStartPosition, transform.position) > reverse)
		{
			reverseStartPosition = Vector3.negativeInfinity;
            e = 0;
			critical_stop = false;
			return;
		}
        vehicle.input.Steering = 0;
        vehicle.input.Vertical = -2f;
    }


    // ОСНОВНОЙ АВТОПИЛОТ
    private void DriveToWaypoint()
    {
        if (currentPointIndex >= waypoints.Count)
        {
            Debug.Log("[Autopilot] Все точки пройдены — стоп.");
            StopTractor();
            drivingBan = true;
            return;
        }

        Transform target = waypoints[currentPointIndex];

        float distance = Vector3.Distance(transform.position, target.position);
        Debug.Log($"[Drive] Target={currentPointIndex}, Dist={distance:F1}");

        if (distance < arrivalDistance)
        {
            currentPointIndex++;
            collector.currentPointIndex = currentPointIndex;
            return;
        }
        // 2) РУЛЕНИЕ
        
        float steerNorm = ComputeSteering();

        Debug.Log($"[steerNorm] turning_side={steerNorm}");
        vehicle.input.Steering = Mathf.MoveTowards(
            vehicle.input.Steering,
            steerNorm,
            Time.deltaTime * steeringSmoothing
        );
      
        // ПРЕДСКАЗАНИЕ ПОВОРОТА
        
        float turnAngle = ComputeTurnAngle();
        float turnDistance = ComputeTurnDistance();

        // Насколько резкий поворот маршрута
        float turnSharpness = Mathf.InverseLerp(0f, minimumSpeedAngle, turnAngle);

        // Насколько близко поворот
        float distanceFactor = Mathf.InverseLerp(slowDownDistance, arrivalDistance, turnDistance);

 		float slowFactor = Mathf.Clamp01(turnSharpness * distanceFactor);
      
	
		// УЧЁТ ТЕКУЩЕГО ПОВОРОТА КОЛЁС 

		// Нормализованный угол поворота колёс
		float wheelSharpness = Mathf.InverseLerp(0f, maxSteerAngle, Mathf.Abs(vehicle.input.Steering));
		// Итоговый коэффициент замедления
		float combinedFactor = Mathf.Clamp01(slowFactor + wheelSharpness * wheelInfluence);

		// Целевая скорость
		float allowedSpeed = Mathf.Lerp(slowTurnSpeed,maxRouteSpeed, 1-combinedFactor);

		Debug.Log($"[TurnPredict] Angle={turnAngle:F1}, Dist={turnDistance:F1}, Wheel={vehicle.input.Steering:F1}, Allowed={allowedSpeed:F1}");

        // 3) СКОРОСТЬ
   
        float currentSpeed = vehicle.Speed * 3.6f;
        float error = allowedSpeed - currentSpeed;

        if (error > 0.2f)
        {
            vehicle.input.Brakes = 0f;
            vehicle.input.Vertical = Mathf.MoveTowards(vehicle.input.Vertical, 1f, Time.deltaTime * accelRate);
            Debug.Log("[Speed] Accelerating");
        }
        else if (error < -0.2f)
        {
            vehicle.input.Vertical = 0f;
            vehicle.input.Brakes = Mathf.MoveTowards(vehicle.input.Brakes, 0.8f, Time.deltaTime * brakeRate);
            Debug.Log("[Speed] Braking");
        }
        else
        {
            vehicle.input.Brakes = 0f;
            vehicle.input.Vertical = Mathf.MoveTowards(vehicle.input.Vertical,0.3f, Time.deltaTime * accelRate);
            Debug.Log("[Speed] Holding");
        }
    }

    private float ComputeTurnAngle()
	{
    	
    	if (currentPointIndex + 1 >= waypoints.Count)
		{
			return 0f;
		}
   		Vector3 carDir = transform.forward;

    	Vector3 routeDir = (waypoints[currentPointIndex + 1].position - waypoints[currentPointIndex].position).normalized;
		// Угол между направлением машины и направлением маршрута
    	return Vector3.Angle(carDir, routeDir);
	}   
private float ComputeTurnDistance()
    {
        if (currentPointIndex + 1 >= waypoints.Count)
            return 999f;

        return Vector3.Distance(lidar.transform.position, waypoints[currentPointIndex+1].position);
    }
	private void UpdateStatus()
	{
		signedSpeed = GetSignedSpeed();
    	displaySpeed = Mathf.Lerp(displaySpeed, signedSpeed, Time.deltaTime * 5f);

    	float absSpeed = Mathf.Abs(displaySpeed);

    	if (Speedometr != null)
    	{
		
        	if (displaySpeed < -0.1f)
            	Speedometr.text = $"R{absSpeed:F1} км/ч";
        	else
            	Speedometr.text = $"{absSpeed:F1} км/ч";
    	}
	}
	float GetSignedSpeed()
    {
        if (tractorRb == null)
            return vehicle.Speed * 3.6f;

        Vector3 localVel = vehicle.transform.InverseTransformDirection(tractorRb.linearVelocity);
        return localVel.z * 3.6f;
    }
    // РАСЧЁТ РУЛЕНИЯ
    private float turning_side = 1;
    private float local_dist = 10f;
    private int left = -1;
	private int right = -1;
    private float ComputeSteering()
    {
		float[] s = lidar.GetSector(0, sector / 2);
		int half = sector / 2;
		left = -1;
	    right = -1;
        int min_dist_index = 0;
		float steerNormD = float.NaN;
        float min_dist = distanceToDetour;
        float[] ds = new float[s.Length];

        for(int i = 0;i < s.Length; ++i)
        {
            float x = Mathf.Abs((float)(i - half) / (float)half);
            float t = x * x;

            ds[i] = distanceFromAngle + (distanceToDetour - distanceFromAngle) * (1- t);
    
            if(s[i]< critical_dist)
            {
                critical_stop = true;
                StopTractor();
                return 0f; 
            }
            if (min_dist > s[i])
            {
                    min_dist_index = i;
                    local_dist = ds[i];
                    min_dist = s[i];
            }
        }
		for (int i = 0; i < s.Length; i++)
		{
    		if (s[i] < ds[i])
    		{
        		left = i;
        		break;
    		}
		}

		for (int i = s.Length - 1; i >= 0; i--)
		{   
    		if (s[i] < ds[i])
    		{
        		right = i;
        		break;
    		}
		}
		// Вычисляем steer
		if (left != -1 || right != -1)
		{
            int distLeft = left;
    		int distRight = (s.Length - 1) - right;
    		if (distLeft < distRight) 
        			steerNormD = +(1f - (float)(distRight+1)/(float)s.Length)*(1f - influenceOfLet) + influenceOfLet*(s[right]/ds[left]);   
    		else if(distLeft > distRight)
        			steerNormD = -(1f - (float)(distLeft+1)/(float)s.Length)*(1f - influenceOfLet) - influenceOfLet*(s[left]/ds[right]);
            else
            {
                float x =   Mathf.Clamp( (float)min_dist_index -  (float)half, -1f, 1f);
                steerNormD = (x==0 ? -1 : x)*((float)(distLeft+1)/(float)s.Length)*(1f - influenceOfLet) + influenceOfLet*(min_dist/ds[min_dist_index]);
                  
            }	
            turnStartPosition = lidar.transform.position;
            if(steerNormD < 0f)
            {
                turning_side = -turnRadius;
            }
            else
            {
                turning_side = turnRadius;
            }
            IsDetour = true;
			steerNormD = Mathf.Clamp(steerNormD, -1f, 1f);	
            Debug.Log($"[ComputeSteering [Luch] {steerNormD}");
		}
        else if(IsDetour)
        {
            float d = Vector3.Distance(turnStartPosition, lidar.transform.position);
            if(d < detourLength)
            {
                Debug.Log($"[detourLength] turning_side={turning_side * (turning_shape - ((float)d/detourLength))}");
                return turning_side * (turning_shape - ((float)d/detourLength));
            }
            else
            {
                IsDetour = false;
            }
        }
        float steerNorm = 0;
        Debug.Log($"[ComputeSteering [lidar - end]");
        Transform target = waypoints[currentPointIndex];
        Vector3 local = transform.InverseTransformPoint(target.position);
        float angle = Mathf.Atan2(local.x, local.z) * Mathf.Rad2Deg;
        steerNorm = Mathf.Clamp(angle / maxSteerAngle, -1f, 1f);  
        if(currentPointIndex == 0)
        {
            return TurnCalculate(steerNormD,steerNorm);
        }
		Debug.Log($"[ComputeSteering [1] {steerNorm:F1}");
        Transform past = waypoints[currentPointIndex-1];
        float dist = DistancePointToSegment(transform.position,past.position,target.position);
        float side = SideOfLine(transform.position,past.position,target.position);
        if(dist < permissibleLimit)
        {	
            return TurnCalculate( steerNormD,steerNorm);
        }
        steerNorm =  steerNorm + (Mathf.Clamp((dist/deviationLimit),0f,1f)*turnToLine*side);
        return TurnCalculate( steerNormD,steerNorm);
    }
    private float TurnCalculate(float steerNormD,float steerNorm)
    {
        steerNorm = Mathf.Clamp(steerNorm, -1f, 1f);
        if(!float.IsNaN(steerNormD))
        {
            steerNormD = Mathf.Clamp(steerNormD, -1f, 1f);
            if((steerNorm < 0f && steerNormD < 0f) || (steerNorm > 0f && steerNormD > 0f))
            {
                return  steerNormD*(0.2f) + (0.8f)*steerNorm;
            }
            else 
            {
                if((right - left) > strength_sector || MathF.Abs(steerNormD)> strength_turn)
                {
                     
                    return steerNormD;
                 
                }
           
            }
        }
        Debug.Log($"steerNorm");
        return  steerNorm;
    }
    float DistancePointToSegment(Vector3 point, Vector3 a, Vector3 b)
    {
        Vector3 ab = b - a;
        Vector3 ap = point - a;
        float sq = ab.sqrMagnitude;
            if (sq < 0.0001f)
                return Vector3.Distance(point, a);
        float t = Vector3.Dot(ap, ab) / sq;
        t = Mathf.Clamp01(t); 

        Vector3 closestPoint = a + ab * t;
        return Vector3.Distance(point, closestPoint);
    }
    float SideOfLine(Vector3 point, Vector3 a, Vector3 b)
    {
        Vector2 p = new Vector2(point.x, point.z);
        Vector2 A = new Vector2(a.x, a.z);
        Vector2 B = new Vector2(b.x, b.z);

        Vector2 AB = B - A;
        Vector2 AP = p - A;

       
        float cross = AB.x * AP.y - AB.y * AP.x;
        if(cross > 0)
        {
            return 1;
        }
        else if(cross < 0)
        {
            return -1;
        }
        else
        {
            return 0;
        }
    }

    // ОСТАНОВКА
    private void StopTractor()
    {
        vehicle.input.Vertical = 0f;
        vehicle.input.Brakes = 1f;
        vehicle.input.Handbrake = 1f;   
        vehicle.input.Steering = 0f;
        vehicle.input.autoSetInput = false;
        Debug.Log("[Autopilot] Tractor stopped.");
    }
    private void ReleaseEmergencyStop()
    {
        vehicle.input.Handbrake = 0f;
        vehicle.input.Brakes = 0f;
        vehicle.input.Vertical = 0f; 
        vehicle.input.autoSetInput = false;
    }


    // ВКЛ/ВЫКЛ
    public void ToggleAutopilot(bool state)
    {
        isAutoMode = state;
        Debug.Log("[ToggleAutopilot = critical_stop]");
        if (state)
        {
            ReleaseEmergencyStop();
            critical_stop = false;
            vehicle.input.autoSetInput = false;
        }
        else
        {
            StopTractor();
        }
    }

}