# API Specification

## 1. Overview

This document defines the REST API contract between the frontend and backend of the Smart Carpark Recommendation System.

The backend is responsible for interacting with external data sources and normalising their data. External APIs such as OneMap, HDB/data.gov.sg, LTA DataMall, and URA are not directly accessed by the frontend.

---

## 2. General Standards

### Base Path

`/api`

### Data Format

Requests and responses use JSON.

`Content-Type: application/json`

### Naming Convention

JSON field names use `camelCase`.

Example:

```json
{
  "arrivalTime": "2026-10-09T14:00:00+08:00",
  "walkingTimeMin": 6
}
```

### Date and Time

Date and time values use ISO 8601 format with timezone information.

Example:

`2026-10-09T14:00:00+08:00`

### Units

| Data | Unit |
|---|---|
| Distance | metres (m) |
| Walking time | minutes (min) |
| Parking duration | minutes |
| Parking fee | SGD |
| Coordinates | WGS84 decimal degrees |
| Occupancy | percentage (0–100) |

### Missing Data

Unavailable information is represented using JSON `null`.

For example:

```json
{
  "availability": null
}
```

A value such as `0` must not be used to represent unavailable data if `0` has an actual meaning.

---

## 3. API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/search` | Search for and rank eligible carparks |
| GET | `/api/carparks/{carparkId}` | Retrieve detailed information about a selected carpark |
| GET | `/api/destinations/search?q={query}` | Search for destination suggestions (optional) |

---

## 4. Search for Carparks

### POST `/api/search`

Searches for eligible carparks within 1 km of the selected destination and ranks them according to the user's preferences.

### Request Body

```json
{
  "destination": "Nanyang Technological University",
  "arrivalTime": "2026-10-09T14:00:00+08:00",
  "durationMinutes": 180,
  "preferences": {
    "pricePriority": 1,
    "walkingDistancePriority": 2,
    "availabilityPriority": 3,
    "lotType": "CAR",
    "carparkType": null,
    "evChargingRequired": false
  }
}
```

### Request Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `destination` | string | Yes | Destination entered or selected by the user |
| `arrivalTime` | string | Yes | Expected arrival time in ISO 8601 format |
| `durationMinutes` | integer | Yes | Expected parking duration in minutes |
| `preferences` | object | Yes | User's ranking and filtering preferences |

### Preference Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `pricePriority` | integer | Yes | Priority assigned to parking price |
| `walkingDistancePriority` | integer | Yes | Priority assigned to walking distance/time |
| `availabilityPriority` | integer | Yes | Priority assigned to parking availability |
| `lotType` | string | Yes | Required vehicle lot type |
| `carparkType` | string or null | No | Optional carpark type filter |
| `evChargingRequired` | boolean | Yes | Whether EV charging is required |

The priority values use the following convention:

- `1` = highest priority
- `2` = second priority
- `3` = lowest priority

The three priority values must be unique.

### Successful Response

**HTTP Status: `200 OK`**

```json
{
  "destination": {
    "query": "Nanyang Technological University",
    "latitude": 1.3483,
    "longitude": 103.6831
  },
  "results": [
    {
      "rank": 1,
      "carparkId": "CARPARK_001",
      "name": "Example Carpark",
      "address": "Example Address",
      "latitude": 1.3490,
      "longitude": 103.6840,
      "carparkType": "MULTI_STOREY",
      "lotType": "CAR",
      "walkingDistanceM": 420,
      "walkingTimeMin": 6,
      "estimatedFeeSgd": 3.60,
      "availability": {
        "availableLots": 47,
        "totalLots": 100,
        "lastUpdated": "2026-10-09T13:58:00+08:00",
        "isStale": false
      },
      "predictedBusyness": {
        "occupancyPercentage": 68,
        "level": "MODERATE"
      },
      "evCharging": {
        "supported": true,
        "availableChargers": 2
      },
      "compositeScore": 0.82
    }
  ]
}
```

The `results` array is ordered from the highest-ranked to the lowest-ranked carpark.

### Search Result Fields

| Field | Type | Description |
|---|---|---|
| `rank` | integer | Final recommendation position |
| `carparkId` | string | Unique internal identifier for the carpark |
| `name` | string | Carpark or development name |
| `address` | string or null | Carpark address |
| `latitude` | number | WGS84 latitude |
| `longitude` | number | WGS84 longitude |
| `carparkType` | string or null | Physical type of carpark |
| `lotType` | string | Vehicle lot category |
| `walkingDistanceM` | integer or null | Walking distance from carpark to destination |
| `walkingTimeMin` | integer or null | Estimated walking time to destination |
| `estimatedFeeSgd` | number or null | Estimated parking fee for the requested duration |
| `availability` | object or null | Current live parking availability |
| `predictedBusyness` | object or null | Predicted busyness at expected arrival time |
| `evCharging` | object | EV charging information |
| `compositeScore` | number | Score used for recommendation ranking |

---

## 5. Live Availability

Live availability uses the following format:

```json
{
  "availableLots": 47,
  "totalLots": 100,
  "lastUpdated": "2026-10-09T13:58:00+08:00",
  "isStale": false
}
```

If live availability information is unavailable:

```json
{
  "availability": null
}
```

`availableLots: 0` must not be used to represent missing availability information because a value of `0` means that there are no available lots.

---

## 6. Predicted Busyness

Predicted busyness uses the following format:

```json
{
  "occupancyPercentage": 68,
  "level": "MODERATE"
}
```

The allowed busyness levels are:

- `LOW`
- `MODERATE`
- `HIGH`

If there is insufficient historical data to generate a prediction:

```json
{
  "predictedBusyness": null
}
```

Predicted busyness represents an estimate based on historical availability data and does not guarantee future availability.

---

## 7. EV Charging

If the carpark is known to support EV charging:

```json
{
  "supported": true,
  "availableChargers": 2
}
```

If the carpark is known not to support EV charging:

```json
{
  "supported": false,
  "availableChargers": 0
}
```

If EV charging information cannot be reliably determined:

```json
{
  "supported": null,
  "availableChargers": null
}
```

If `evChargingRequired` is `true`, only carparks with known EV charging support are returned.

---

## 8. Carpark Details

### GET `/api/carparks/{carparkId}`

Returns detailed information about a selected carpark.

Example request:

`GET /api/carparks/CARPARK_001`

### Successful Response

**HTTP Status: `200 OK`**

```json
{
  "carparkId": "CARPARK_001",
  "name": "Example Carpark",
  "address": "Example Address",
  "location": {
    "latitude": 1.3490,
    "longitude": 103.6840
  },
  "carparkType": "MULTI_STOREY",
  "parkingSystem": "ELECTRONIC",
  "freeParking": "SUN_PUBLIC_HOLIDAY",
  "nightParking": true,
  "parkingRates": [
    {
      "dayType": "WEEKDAY",
      "startTime": "07:00",
      "endTime": "22:30",
      "rateSgd": 0.60,
      "billingIntervalMinutes": 30,
      "maximumChargeSgd": null
    }
  ],
  "availability": {
    "availableLots": 47,
    "totalLots": 100,
    "lastUpdated": "2026-10-09T13:58:00+08:00",
    "isStale": false
  },
  "evCharging": {
    "supported": true,
    "availableChargers": 2
  }
}
```

---

## 9. Destination Search

### GET `/api/destinations/search?q={query}`

This endpoint is optional and is only required if destination autocomplete or destination suggestions are implemented in the frontend.

Example request:

`GET /api/destinations/search?q=ntu`

### Successful Response

**HTTP Status: `200 OK`**

```json
{
  "suggestions": [
    {
      "name": "Nanyang Technological University",
      "address": "50 Nanyang Avenue, Singapore",
      "latitude": 1.3483,
      "longitude": 103.6831
    }
  ]
}
```

The backend retrieves and normalises the destination information using OneMap.

---

## 10. Error Handling

All API errors use a common response format.

```json
{
  "error": {
    "code": "INVALID_SEARCH_REQUEST",
    "message": "Arrival time must not be earlier than the current time."
  }
}
```

### Error Codes

| Error Code | Meaning |
|---|---|
| `INVALID_SEARCH_REQUEST` | Search parameters are invalid |
| `INVALID_DESTINATION` | Destination cannot be resolved |
| `CARPARK_NOT_FOUND` | Requested carpark does not exist |
| `NO_CARPARKS_FOUND` | No supported carparks were found within 1 km |
| `EXTERNAL_SERVICE_UNAVAILABLE` | A required external service is unavailable |
| `INTERNAL_SERVER_ERROR` | An unexpected backend error occurred |

### HTTP Status Codes

| Status Code | Meaning |
|---|---|
| `200 OK` | Request completed successfully |
| `400 Bad Request` | Invalid request |
| `404 Not Found` | Requested resource was not found |
| `422 Unprocessable Entity` | Request failed schema validation |
| `500 Internal Server Error` | Unexpected backend error |
| `503 Service Unavailable` | Required external service is temporarily unavailable |

---

## 11. Enumerations

### Lot Type

Initial standard values:

- `CAR`
- `MOTORCYCLE`
- `HEAVY_VEHICLE`

The final supported values should correspond to the lot types supported by the application.

### Predicted Busyness Level

- `LOW`
- `MODERATE`
- `HIGH`

### Carpark Type

The final normalised carpark type values will be determined based on the carpark types provided by the supported external data sources.

---

## 12. External Data Normalisation

The backend is responsible for retrieving and normalising data from external services.

The frontend must not depend on the original response formats used by the external APIs.

### OneMap

Used for:

- Destination geocoding
- Walking route, distance, and time

### HDB / data.gov.sg

Used for:

- HDB carpark information
- HDB live carpark availability

### LTA DataMall

Used for:

- Supported live carpark availability
- EV charging information

### URA

Used for:

- URA carpark information where applicable

All coordinates exposed through this API use WGS84 latitude and longitude.

---

## 13. Internal Backend Processing

The following are internal backend responsibilities and are not exposed as separate frontend API endpoints:

- Search validation
- Candidate carpark retrieval and filtering
- Walking time and distance estimation
- Parking fee calculation
- Live availability retrieval
- Availability prediction
- EV charging data retrieval
- Recommendation and ranking
- Historical availability collection

The Historical Availability Collector periodically retrieves supported live availability data and stores historical records in MySQL.

Therefore, separate public endpoints such as `/api/predict`, `/api/calculate-fee`, or `/api/historical-availability` are not required.