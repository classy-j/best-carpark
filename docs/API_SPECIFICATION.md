# API Specification

## 1. Overview

This document defines the REST API contract between the frontend and backend of the Smart Carpark Recommendation System.

The backend is responsible for interacting with external data sources and normalising their data. External APIs such as OneMap, HDB/data.gov.sg, LTA DataMall, and other supported data sources are not directly accessed by the frontend.

---

## 2. General Standards

### Base Path

The versioned API base path is:

`/api/v1`

The health-check endpoint is unversioned:

`/health`

### Data Format

Requests and responses use JSON.

`Content-Type: application/json`

### Naming Convention

JSON field names use `snake_case` to match the backend Pydantic models.

Example:

```json
{
  "arrival_time": "2026-10-09T14:00:00+08:00",
  "walking_time_min": 6.0
}
```

### Date and Time

Date and time values use ISO 8601 format.

Example:

`2026-10-09T14:00:00+08:00`

Timezone-aware values are converted to Singapore Time by the backend. Naive date-time values received from the frontend are interpreted as Singapore Time.

### Units

| Data | Unit |
|---|---|
| Distance | metres (m) |
| Walking time | minutes (min) |
| Parking duration | minutes |
| Parking fee | SGD |
| Vehicle/gantry height | metres (m) |
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

A value such as `0` must not be used to represent unavailable data when `0` has an actual meaning.

---

## 3. API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/v1/search` | Search for and rank eligible carparks |
| GET | `/api/v1/carparks/{carpark_id}` | Retrieve information about a selected carpark |
| GET | `/api/v1/carparks/{carpark_id}/availability` | Retrieve current availability for a carpark |
| GET | `/api/v1/carparks/{carpark_id}/expected-busyness` | Retrieve expected busyness for a carpark |
| GET | `/health` | Check whether the backend is running |

Destination resolution is handled as part of `POST /api/v1/search`. A separate public destination-search endpoint is not currently exposed.

---

## 4. Search for Carparks

### POST `/api/v1/search`

Searches for eligible carparks within 1 km of the selected destination and ranks them according to the user's preferences.

### Request Body

A request using parking duration may be sent as:

```json
{
  "destination_address": "Nanyang Technological University",
  "arrival_time": "2026-10-09T14:00:00+08:00",
  "parking_duration_minutes": 180,
  "preference": {
    "priority_ranking": [
      "PRICE",
      "WALKING_TIME",
      "AVAILABILITY"
    ],
    "lot_type": "CAR",
    "vehicle_height_m": null,
    "carpark_types": [],
    "ev_required": false
  }
}
```

Alternatively, the client may provide a departure time:

```json
{
  "destination_address": "Nanyang Technological University",
  "arrival_time": "2026-10-09T14:00:00+08:00",
  "departure_time": "2026-10-09T17:00:00+08:00",
  "preference": {
    "priority_ranking": [
      "PRICE",
      "WALKING_TIME",
      "AVAILABILITY"
    ],
    "lot_type": "CAR",
    "vehicle_height_m": null,
    "carpark_types": [],
    "ev_required": false
  }
}
```

### Request Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `destination_address` | string | Yes | Destination entered or selected by the user |
| `destination_location` | object or null | No | Coordinates of a destination selected after multiple OneMap matches are returned |
| `arrival_time` | string | Yes | Expected arrival time in ISO 8601 format |
| `departure_time` | string or null | Conditional | Intended departure time |
| `parking_duration_minutes` | integer or null | Conditional | Intended parking duration in minutes |
| `preference` | object | No | User ranking and filtering preferences; backend defaults are used when omitted |

At least one of `departure_time` or `parking_duration_minutes` must be provided.

If `departure_time` is omitted and `parking_duration_minutes` is provided, the backend calculates the departure time from the arrival time and parking duration.

If both fields are provided, the supplied `departure_time` is used.

The departure time must be later than the arrival time.

`parking_duration_minutes` must be greater than zero and cannot exceed 7 days.

### Destination Location

When the user selects one of several matching destinations, the selected coordinates may be resubmitted as:

```json
{
  "destination_location": {
    "latitude": 1.3483,
    "longitude": 103.6831
  }
}
```

When `destination_location` is supplied, the backend uses those coordinates rather than geocoding the address again.

### Preference Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `priority_ranking` | array of strings | No | Ranking factors in priority order |
| `lot_type` | string | No | Required vehicle lot type |
| `vehicle_height_m` | number or null | No | Vehicle height used for gantry-height filtering |
| `carpark_types` | array of strings | No | Allowed carpark types; empty means any type |
| `ev_required` | boolean | No | Whether known EV charging support is required |

Default ranking priorities are:

```json
[
  "PRICE",
  "WALKING_TIME",
  "AVAILABILITY"
]
```

Supported ranking factors are:

- `PRICE`
- `WALKING_TIME`
- `AVAILABILITY`
- `EV_CHARGING`

Supported lot types are:

- `CAR`
- `MOTORCYCLE`
- `HEAVY_VEHICLE`

The backend also normalises the following ranking aliases:

| Alias | Normalised value |
|---|---|
| `COST` | `PRICE` |
| `DISTANCE` | `WALKING_TIME` |
| `WALKING` | `WALKING_TIME` |
| `EV` | `EV_CHARGING` |

### Successful Response

**HTTP Status: `200 OK`**

```json
{
  "destination_address": "Nanyang Technological University",
  "destination": {
    "latitude": 1.3483,
    "longitude": 103.6831
  },
  "results": [
    {
      "rank": 1,
      "carpark": {
        "carpark_id": "CARPARK_001",
        "name": "Example Carpark",
        "address": "Example Address",
        "location": {
          "latitude": 1.349,
          "longitude": 103.684
        },
        "carpark_type": "MULTI_STOREY",
        "parking_system": "ELECTRONIC",
        "gantry_height_m": 2.1,
        "night_parking": true,
        "free_parking": null,
        "short_term_parking": "WHOLE_DAY",
        "has_ev_charging": true
      },
      "straight_line_m": 350.4,
      "walking_distance_m": 420,
      "walking_time_min": 6.0,
      "estimated_fee_sgd": 3.60,
      "availability": {
        "available_lots": 47,
        "total_lots": 100,
        "occupancy_pct": 53,
        "last_updated": "2026-10-09T13:58:00+08:00",
        "is_stale": false
      },
      "expected_busyness": {
        "occupancy_pct": 68,
        "level": "MODERATE",
        "sample_count": 24
      },
      "ev_charging": {
        "supported": true,
        "available_chargers": 2
      },
      "height_unknown": false,
      "composite_score": 0.82
    }
  ],
  "message": null
}
```

The `results` array is ordered from the highest-ranked to the lowest-ranked carpark.

### Search Result Fields

| Field | Type | Description |
|---|---|---|
| `rank` | integer | Final recommendation position |
| `carpark` | object | Normalised carpark information |
| `straight_line_m` | number or null | Straight-line distance from the carpark to the destination |
| `walking_distance_m` | integer or null | Walking distance returned by OneMap |
| `walking_time_min` | number or null | Estimated walking time to the destination |
| `estimated_fee_sgd` | number or null | Estimated parking fee for the requested parking period |
| `availability` | object or null | Current live parking availability |
| `expected_busyness` | object or null | Expected busyness at the requested arrival time |
| `ev_charging` | object | EV charging information |
| `height_unknown` | boolean | True when vehicle height was supplied but the carpark gantry height is unknown |
| `composite_score` | number | Score used for recommendation ranking |

If no supported carparks are found within the configured 1 km radius, the search response contains an empty `results` array and a message explaining that no carparks were found.

---

## 5. Multiple Destination Matches

Destination resolution is performed as part of `POST /api/v1/search`.

If OneMap returns several possible destinations and no exact/single result can be selected automatically, the backend returns:

**HTTP Status: `409 Conflict`**

```json
{
  "detail": "Several places match the destination. Pick one.",
  "matches": [
    {
      "name": "Example Destination",
      "address": "Example Address",
      "location": {
        "latitude": 1.3483,
        "longitude": 103.6831
      }
    }
  ]
}
```

The frontend displays the possible matches to the user.

After the user selects one, the frontend resubmits the search request with `destination_location` containing the selected coordinates.

---

## 6. Live Availability

Live availability uses the following format:

```json
{
  "available_lots": 47,
  "total_lots": 100,
  "occupancy_pct": 53,
  "last_updated": "2026-10-09T13:58:00+08:00",
  "is_stale": false
}
```

`total_lots` and `occupancy_pct` may be `null` when the source does not provide enough information.

If live availability information is unavailable, the search result contains:

```json
{
  "availability": null
}
```

`available_lots: 0` represents a carpark with no currently available lots and must not be used to represent missing data.

Availability older than the configured freshness threshold is marked using:

```json
{
  "is_stale": true
}
```

---

## 7. Expected Busyness

Expected busyness is calculated from historical availability data for the user's intended arrival time.

The response format is:

```json
{
  "occupancy_pct": 68,
  "level": "MODERATE",
  "sample_count": 24
}
```

The allowed busyness levels are:

- `LOW`
- `MODERATE`
- `HIGH`

If there is insufficient historical information to generate an estimate:

```json
{
  "expected_busyness": null
}
```

Expected busyness is an estimate based on historical availability and does not guarantee actual future availability.

---

## 8. EV Charging

EV charging information is attached to each search result.

The current shared response model is:

```json
{
  "supported": true,
  "available_chargers": 2
}
```

If a carpark is known not to support EV charging:

```json
{
  "supported": false,
  "available_chargers": null
}
```

If EV charging support cannot be reliably determined:

```json
{
  "supported": null,
  "available_chargers": null
}
```

When `ev_required` is `true`, the search applies the EV charging requirement to candidate carparks.

The EV integration may be extended with additional charging information such as total charger count or connector types. If the shared backend response schema is extended, this section must be updated accordingly.

---

## 9. Carpark Information

### GET `/api/v1/carparks/{carpark_id}`

Returns the stored information for a selected carpark.

Example request:

`GET /api/v1/carparks/CARPARK_001`

### Successful Response

**HTTP Status: `200 OK`**

```json
{
  "carpark_id": "CARPARK_001",
  "name": "Example Carpark",
  "address": "Example Address",
  "location": {
    "latitude": 1.349,
    "longitude": 103.684
  },
  "carpark_type": "MULTI_STOREY",
  "parking_system": "ELECTRONIC",
  "gantry_height_m": 2.1,
  "night_parking": true,
  "free_parking": null,
  "short_term_parking": "WHOLE_DAY",
  "has_ev_charging": true
}
```

If the carpark does not exist, the endpoint returns `404 Not Found`.

---

## 10. Carpark Availability Endpoint

### GET `/api/v1/carparks/{carpark_id}/availability`

Returns current availability for a selected carpark and lot type.

The optional query parameter is:

`lot_type`

The default value is:

`CAR`

Example:

`GET /api/v1/carparks/CARPARK_001/availability?lot_type=CAR`

### Successful Response

**HTTP Status: `200 OK`**

```json
{
  "available_lots": 47,
  "total_lots": 100,
  "occupancy_pct": 53,
  "last_updated": "2026-10-09T13:58:00+08:00",
  "is_stale": false
}
```

If the carpark exists but no current availability is available, the endpoint returns:

```json
null
```

If the carpark does not exist, the endpoint returns `404 Not Found`.

---

## 11. Expected Busyness Endpoint

### GET `/api/v1/carparks/{carpark_id}/expected-busyness`

Returns the expected busyness of a selected carpark based on historical availability.

Supported query parameters are:

| Parameter | Required | Description |
|---|---|---|
| `lot_type` | No | Lot type to estimate; defaults to `CAR` |
| `at` | No | Arrival time in ISO 8601 format; defaults to the current Singapore time |

Example:

`GET /api/v1/carparks/CARPARK_001/expected-busyness?lot_type=CAR&at=2026-10-09T14:00:00%2B08:00`

### Successful Response

**HTTP Status: `200 OK`**

```json
{
  "occupancy_pct": 68,
  "level": "MODERATE",
  "sample_count": 24
}
```

If insufficient historical information exists, the endpoint returns:

```json
null
```

If the carpark does not exist, the endpoint returns `404 Not Found`.

---

## 12. Health Check

### GET `/health`

Used to verify that the backend application is running.

### Successful Response

**HTTP Status: `200 OK`**

```json
{
  "status": "ok"
}
```

---

## 13. Error Handling

### Invalid Destination

If OneMap cannot resolve the destination:

**HTTP Status: `404 Not Found`**

```json
{
  "detail": "No OneMap result for 'Example Destination'"
}
```

### Multiple Destinations

If several destinations match:

**HTTP Status: `409 Conflict`**

```json
{
  "detail": "Several places match the destination. Pick one.",
  "matches": [
    {
      "name": "Example Destination",
      "address": "Example Address",
      "location": {
        "latitude": 1.3483,
        "longitude": 103.6831
      }
    }
  ]
}
```

### Invalid Request

If request data fails Pydantic validation, such as when the departure time is before the arrival time:

**HTTP Status: `422 Unprocessable Entity`**

FastAPI returns validation information in the `detail` field.

### External API Failure

If an external API such as OneMap, HDB/data.gov.sg, or LTA cannot provide the required data:

**HTTP Status: `502 Bad Gateway`**

```json
{
  "detail": "An external data service is unavailable."
}
```

### Carpark Not Found

If a requested carpark does not exist:

**HTTP Status: `404 Not Found`**

```json
{
  "detail": "Carpark 'CARPARK_001' not found"
}
```

---

## 14. Internal Service Interfaces

The frontend communicates with the backend through the REST endpoints defined above.

Internal backend operations are implemented as service and repository interfaces and are not exposed as separate frontend API endpoints.

These include:

- destination geocoding and OneMap destination matching
- candidate carpark retrieval and filtering
- walking time and distance estimation
- parking fee calculation
- live availability retrieval
- expected busyness estimation
- EV charging retrieval and carpark association
- recommendation and ranking
- historical availability collection

The Historical Availability Collector periodically retrieves supported live availability data and stores historical records in MySQL.

Therefore, separate public endpoints such as `/api/v1/predict`, `/api/v1/calculate-fee`, or `/api/v1/historical-availability` are not required.