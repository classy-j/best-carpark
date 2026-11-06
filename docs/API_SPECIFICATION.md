# API Specification

## 1. Overview

This document defines the REST API contract between the frontend and backend of the Best Carpark App.

The backend is responsible for retrieving, normalising and processing data from external services and the MySQL database. External APIs such as OneMap, HDB/data.gov.sg, URA Data Service and LTA DataMall are accessed by the backend rather than directly by the frontend.

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
  "arrival_time": "2026-11-10T14:00:00+08:00",
  "walking_time_min": 6.0
}
```

### Date and Time

Date and time values use ISO 8601 format.

Example:

`2026-11-10T14:00:00+08:00`

Timezone-aware values are converted to Singapore Time by the backend.

Naive date-time values received from the frontend are interpreted as Singapore Time.

### Units

| Data | Unit |
|---|---|
| Distance | metres (m) |
| Walking time | minutes (min) |
| Parking duration | minutes |
| Parking fee | SGD |
| Vehicle / gantry height | metres (m) |
| Coordinates | WGS84 decimal degrees |
| Occupancy | percentage (0–100) |

### Missing Data

Unavailable information is represented using JSON `null`.

Example:

```json
{
  "availability": null
}
```

A value such as `0` must not be used to represent unavailable data when `0` has an actual meaning.

For example:

- `available_lots: 0` means that no parking lots are currently available.
- `available_chargers: 0` means that EV charging is supported but no chargers are currently available.
- `null` means that the information is unavailable or cannot be determined.

---

## 3. API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/v1/search` | Search for and rank eligible carparks |
| GET | `/api/v1/carparks/{carpark_id}` | Retrieve information about a selected carpark |
| GET | `/api/v1/carparks/{carpark_id}/availability` | Retrieve current availability for a carpark |
| GET | `/api/v1/carparks/{carpark_id}/expected-busyness` | Retrieve expected busyness for a carpark |
| GET | `/health` | Check whether the backend is running |

Destination resolution is handled as part of `POST /api/v1/search`.

A separate public destination-search endpoint is not currently exposed.

---

# 4. Search for Carparks

## POST `/api/v1/search`

Searches for eligible carparks within the configured 1 km radius of the selected destination.

The backend:

1. validates and resolves the destination;
2. finds supported carparks within 1 km;
3. applies the configured carpark, lot-type, vehicle-height and EV filters;
4. obtains parking fee, availability and expected busyness information;
5. obtains OneMap walking routes for up to the 20 nearest eligible carparks;
6. ranks the routed carparks according to the user's ranking preferences; and
7. places eligible carparks without a verified walking route after the routed carparks.

---

## 4.1 Request Body

A request using parking duration may be sent as:

```json
{
  "destination_address": "Nanyang Technological University",
  "arrival_time": "2026-11-10T14:00:00+08:00",
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
  "arrival_time": "2026-11-10T14:00:00+08:00",
  "departure_time": "2026-11-10T17:00:00+08:00",
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

---

## 4.2 Request Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `destination_address` | string | Yes | Destination entered or selected by the user |
| `destination_location` | object or null | No | Coordinates of a destination selected after multiple OneMap matches |
| `arrival_time` | string | Yes | Intended arrival time in ISO 8601 format |
| `departure_time` | string or null | Conditional | Intended departure time |
| `parking_duration_minutes` | integer or null | Conditional | Intended parking duration in minutes |
| `preference` | object | No | Ranking and filtering preferences; defaults are used when omitted |

At least one of `departure_time` or `parking_duration_minutes` must be provided.

If `departure_time` is omitted and `parking_duration_minutes` is supplied, the backend calculates the departure time using:

`departure_time = arrival_time + parking_duration_minutes`

If both `departure_time` and `parking_duration_minutes` are supplied, the supplied `departure_time` is used.

The departure time must be later than the arrival time.

`parking_duration_minutes` must:

- be greater than zero; and
- not exceed 7 days.

The search endpoint also rejects arrival times that are more than approximately 15 minutes in the past.

---

## 4.3 Destination Location

When multiple destinations match the entered address, the frontend allows the Driver to select the intended destination.

The selected coordinates may then be resubmitted:

```json
{
  "destination_location": {
    "latitude": 1.3483,
    "longitude": 103.6831
  }
}
```

When `destination_location` is supplied, the backend uses those coordinates instead of geocoding the destination again.

---

## 4.4 Preference Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `priority_ranking` | array of strings | No | Ranking factors in priority order |
| `lot_type` | string | No | Required vehicle lot type |
| `vehicle_height_m` | number or null | No | Vehicle height used for gantry-height filtering |
| `carpark_types` | array of strings | No | Preferred/allowed carpark types; an empty array means any type |
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

EV charging is a filtering requirement and is not a ranking factor.

Supported lot types are:

- `CAR`
- `MOTORCYCLE`
- `HEAVY_VEHICLE`

The backend normalises the following ranking aliases:

| Alias | Normalised value |
|---|---|
| `COST` | `PRICE` |
| `DISTANCE` | `WALKING_TIME` |
| `WALKING` | `WALKING_TIME` |

Duplicate ranking factors are removed while preserving the first occurrence.

---

## 4.5 Filtering Behaviour

Before ranking, the backend filters the candidate carparks according to the supplied preferences.

### Search Radius

Only supported carparks within 1000 m straight-line distance of the destination are considered.

### Carpark Type

If `carpark_types` is non-empty, only matching carpark types are considered.

If it is empty, all supported carpark types are allowed.

### EV Charging

If:

```json
{
  "ev_required": true
}
```

only carparks with known EV charging support are considered.

### Lot Type

Carparks known not to support the selected lot type are excluded.

URA carparks are represented by vehicle category. A URA carpark with no parking-rate rules for the selected lot type is treated as not supporting that lot type.

### Vehicle Height

If `vehicle_height_m` is supplied:

- carparks with a known gantry height lower than the vehicle height are excluded;
- non-URA carparks with unknown gantry height remain eligible and are marked using `height_unknown: true`;
- URA parking locations do not use the HDB-style gantry-height warning.

---

## 4.6 Successful Response

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
      "straight_line_m": 350,
      "walking_distance_m": 420,
      "walking_time_min": 6.0,
      "walking_time_estimated": false,
      "estimated_fee_sgd": 3.60,
      "availability": {
        "available_lots": 47,
        "total_lots": 100,
        "occupancy_pct": 53,
        "last_updated": "2026-11-10T13:58:00+08:00",
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

---

## 4.7 Search Result Fields

| Field | Type | Description |
|---|---|---|
| `rank` | integer | Final display position |
| `carpark` | object | Normalised carpark information |
| `straight_line_m` | number or null | Straight-line distance from the carpark to the destination |
| `walking_distance_m` | integer or null | Walking distance returned by OneMap |
| `walking_time_min` | number or null | Walking time returned by OneMap |
| `walking_time_estimated` | boolean | Whether the walking time is an approximate value rather than a verified OneMap route |
| `estimated_fee_sgd` | number or null | Estimated parking fee for the requested parking period |
| `availability` | object or null | Latest stored parking availability |
| `expected_busyness` | object or null | Expected busyness at the requested arrival time |
| `ev_charging` | object | EV charging information |
| `height_unknown` | boolean | Whether a supplied vehicle height cannot be checked because the non-URA carpark's gantry height is unknown |
| `composite_score` | number | Composite suitability score used in ranking |

In the current implementation, verified walking times are obtained only for up to the 20 eligible carparks nearest to the destination.

For eligible carparks without a verified route:

```json
{
  "walking_distance_m": null,
  "walking_time_min": null,
  "walking_time_estimated": false
}
```

These unrouted carparks remain eligible but are placed after all carparks with verified OneMap routes.

The frontend presents them under the **Other nearby carparks** section.

---

## 4.8 No Results

If no supported carparks exist within the configured search radius:

```json
{
  "destination_address": "Example Destination",
  "destination": {
    "latitude": 1.3000,
    "longitude": 103.8000
  },
  "results": [],
  "message": "No carparks found within 1 km of the destination."
}
```

If carparks exist within the search radius but all are removed by the selected filters:

```json
{
  "destination_address": "Example Destination",
  "destination": {
    "latitude": 1.3000,
    "longitude": 103.8000
  },
  "results": [],
  "message": "No carparks within 1 km satisfy the selected requirements."
}
```

---

# 5. Multiple Destination Matches

Destination resolution occurs as part of:

`POST /api/v1/search`

If OneMap returns several possible destinations and no exact/single result can be automatically selected, the backend returns:

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

The frontend displays the possible matches to the Driver.

After the Driver selects one, the search request is resubmitted with the selected `destination_location`.

---

# 6. Ranking

The ranking engine uses the following three factors:

- parking price;
- verified OneMap walking time; and
- parking availability.

Ranking priority is determined by `priority_ranking`.

The first configured priority receives the greatest weight, followed by progressively smaller weights for lower-priority factors.

A factor that is unavailable for a particular carpark is omitted from that carpark's weighted average rather than being treated as zero.

### Availability Ranking

For availability ranking:

1. expected busyness at the user's arrival time is preferred when available;
2. otherwise current occupancy percentage is used;
3. if total lot capacity is unavailable, current available-lot count is used as a fallback.

### Tie-Breaking

For routed carparks with equal suitability scores:

1. shorter verified walking time is preferred;
2. if still tied, lower estimated parking fee is preferred.

Carparks without verified OneMap routes are always displayed after routed carparks.

Among unrouted carparks, the composite score is considered first and straight-line distance is used as an additional ordering factor.

---

# 7. Live Availability

Live availability uses the following format:

```json
{
  "available_lots": 47,
  "total_lots": 100,
  "occupancy_pct": 53,
  "last_updated": "2026-11-10T13:58:00+08:00",
  "is_stale": false
}
```

Fields:

| Field | Description |
|---|---|
| `available_lots` | Current number of available lots |
| `total_lots` | Total lots where known |
| `occupancy_pct` | Calculated occupancy percentage where total capacity is known |
| `last_updated` | Timestamp of the stored reading |
| `is_stale` | Whether the reading is older than 15 minutes |

`total_lots` and `occupancy_pct` may be `null` when the source does not provide enough information.

If current availability is unavailable:

```json
{
  "availability": null
}
```

`available_lots: 0` means that there are currently no available lots.

Availability information is obtained from the latest readings stored in MySQL rather than by calling the external availability source during each user search.

The background collector normally refreshes supported availability information every 10 minutes.

---

# 8. Expected Busyness

Expected busyness is derived from stored historical parking availability.

For the requested arrival time, the backend retrieves historical records:

- for the same carpark;
- for the selected lot type;
- on the same weekday;
- around the same 15-minute time slot; and
- from the previous 56 days (8 weeks).

At least 3 usable historical observations are required.

The response format is:

```json
{
  "occupancy_pct": 68,
  "level": "MODERATE",
  "sample_count": 24
}
```

Fields:

| Field | Description |
|---|---|
| `occupancy_pct` | Average historical occupancy percentage |
| `level` | Simplified busyness classification |
| `sample_count` | Number of historical records used |

Busyness levels are:

- `LOW`
- `MODERATE`
- `HIGH`

The current classification thresholds are:

- `LOW`: occupancy ≤ 70%
- `MODERATE`: occupancy > 70% and ≤ 90%
- `HIGH`: occupancy > 90%

If fewer than 3 usable historical observations are available:

```json
{
  "expected_busyness": null
}
```

Expected busyness represents typical historical conditions and is not a formal prediction or guarantee of future parking availability.

---

# 9. EV Charging

EV charging information is attached to each search result.

The response format is:

```json
{
  "supported": true,
  "available_chargers": 2
}
```

### Known EV Support

```json
{
  "supported": true,
  "available_chargers": 2
}
```

### Known No EV Support

```json
{
  "supported": false,
  "available_chargers": null
}
```

### Unknown EV Information

```json
{
  "supported": null,
  "available_chargers": null
}
```

EV stations obtained from LTA DataMall are associated with carparks using proximity matching.

A station is matched to a carpark when it lies within the configured 75 m matching radius.

EV station data is refreshed periodically in the background.

The scheduled refresh interval is approximately one hour.

If the current process has a sufficiently fresh EV feed, `available_chargers` may contain the aggregated number of available charging points from nearby matched EV stations.

If the live EV feed is unavailable or more than approximately one hour old:

- stored EV support information may still be used; but
- `available_chargers` is returned as `null`.

When:

```json
{
  "ev_required": true
}
```

only carparks with known EV charging support are considered eligible.

EV charging is not included in the composite ranking score.

---

# 10. Carpark Information

## GET `/api/v1/carparks/{carpark_id}`

Returns the stored information for a selected carpark.

Example:

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

Fields may be `null` where the corresponding source information is unavailable.

If the carpark does not exist:

**HTTP Status: `404 Not Found`**

```json
{
  "detail": "Carpark 'CARPARK_001' not found"
}
```

---

# 11. Carpark Availability Endpoint

## GET `/api/v1/carparks/{carpark_id}/availability`

Returns the latest stored availability for a selected carpark and lot type.

### Query Parameters

| Parameter | Required | Description |
|---|---|---|
| `lot_type` | No | Lot type to retrieve; defaults to `CAR` |

Supported values are:

- `CAR`
- `MOTORCYCLE`
- `HEAVY_VEHICLE`

Example:

`GET /api/v1/carparks/CARPARK_001/availability?lot_type=CAR`

### Successful Response

**HTTP Status: `200 OK`**

```json
{
  "available_lots": 47,
  "total_lots": 100,
  "occupancy_pct": 53,
  "last_updated": "2026-11-10T13:58:00+08:00",
  "is_stale": false
}
```

If the carpark exists but no availability reading exists:

```json
null
```

If the carpark does not exist:

**HTTP Status: `404 Not Found`**

---

# 12. Expected Busyness Endpoint

## GET `/api/v1/carparks/{carpark_id}/expected-busyness`

Returns the expected busyness for a selected carpark based on historical availability.

### Query Parameters

| Parameter | Required | Description |
|---|---|---|
| `lot_type` | No | Lot type to estimate; defaults to `CAR` |
| `at` | No | Arrival date/time in ISO 8601 format; defaults to current Singapore time |

Example:

`GET /api/v1/carparks/CARPARK_001/expected-busyness?lot_type=CAR&at=2026-11-10T14:00:00%2B08:00`

### Successful Response

**HTTP Status: `200 OK`**

```json
{
  "occupancy_pct": 68,
  "level": "MODERATE",
  "sample_count": 24
}
```

If insufficient historical information exists:

```json
null
```

If the carpark does not exist:

**HTTP Status: `404 Not Found`**

---

# 13. Health Check

## GET `/health`

Used to verify that the FastAPI backend is running.

### Successful Response

**HTTP Status: `200 OK`**

```json
{
  "status": "ok"
}
```

---

# 14. Error Handling

## 14.1 Invalid Destination

If OneMap cannot resolve the entered destination:

**HTTP Status: `404 Not Found`**

Example:

```json
{
  "detail": "Destination 'Example Destination' could not be found."
}
```

---

## 14.2 Multiple Destinations

If several places match the destination:

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

---

## 14.3 Invalid Search Request

If request data fails schema validation:

**HTTP Status: `422 Unprocessable Entity`**

Examples include:

- blank destination;
- missing both parking duration and departure time;
- non-positive parking duration;
- parking duration longer than 7 days;
- departure time not later than arrival time;
- unsupported lot type;
- unsupported ranking factor;
- invalid vehicle height.

FastAPI returns validation details in the `detail` field.

---

## 14.4 Arrival Time in the Past

The search endpoint performs an additional server-side check.

If the intended arrival is more than approximately 15 minutes in the past:

**HTTP Status: `422 Unprocessable Entity`**

```json
{
  "detail": "Arrival time can't be in the past."
}
```

---

## 14.5 External API Failure

If an external API fails during an operation that requires it:

**HTTP Status: `502 Bad Gateway`**

```json
{
  "detail": "An external data service is unavailable."
}
```

External API failures that occur during background collection may instead be logged and retried at a later scheduled collection cycle so that previously stored information remains usable.

---

## 14.6 Carpark Not Found

If a requested carpark does not exist:

**HTTP Status: `404 Not Found`**

Example:

```json
{
  "detail": "Carpark 'CARPARK_001' not found"
}
```

---

# 15. External Data Interfaces

The backend integrates with the following external services.

## OneMap

Used for:

- destination geocoding;
- multiple-destination matching; and
- walking route distance and duration.

Walking routes are cached by the backend for approximately one hour.

## HDB / data.gov.sg

Used for:

- HDB carpark static information; and
- HDB carpark availability.

Availability readings are stored in MySQL by the background collector.

## URA Data Service

Used for supported URA:

- carpark / parking-lot information;
- parking availability; and
- parking-rate information.

URA support depends on valid URA API credentials being configured.

## LTA DataMall

Used for EV charging station information.

EV stations are matched to carparks using the configured 75 m proximity threshold.

---

# 16. Internal Backend Processing

The frontend communicates with the backend only through the REST endpoints defined in this document.

The following operations are internal backend responsibilities and are not exposed as separate public frontend endpoints:

- destination geocoding;
- search validation;
- nearby-carpark retrieval;
- lot-type filtering;
- vehicle-height filtering;
- carpark-type filtering;
- EV-required filtering;
- walking-route retrieval;
- parking-fee calculation;
- live availability retrieval;
- expected busyness estimation;
- EV station association;
- recommendation scoring;
- ranking and tie-breaking;
- HDB/URA availability collection;
- HDB historical availability backfill;
- carpark information refresh; and
- EV data refresh.

The current background processes persist the relevant carpark, rate and availability information in MySQL so that user searches do not need to call every external API synchronously.

Separate public endpoints such as:

- `/api/v1/calculate-fee`
- `/api/v1/predict`
- `/api/v1/historical-availability`

are therefore not required.