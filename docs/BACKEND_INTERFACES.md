# Backend Module Interfaces

This document defines the main interfaces between backend modules.

The exact internal implementation may change, but changes to these interfaces should be communicated to the team before dependent modules are modified.

---

## SearchService

Coordinates the overall carpark search process.

### searchCarparks

Input:

- destination
- arrivalTime
- departureTime or durationMinutes
- SearchPreference

Output:

- ordered list of SearchResult objects

Responsibilities:

- validate request
- obtain destination coordinates
- retrieve candidate carparks
- request walking time
- request fee calculations
- obtain availability
- obtain expected busyness
- obtain EV charging information
- call RankingEngine

---

## GeocodingService

### geocodeDestination

Input:

- destination: string

Output:

- Destination containing name and Location

Uses OneMap.

---

## RoutingService

### getWalkingRoute

Input:

- carparkLocation
- destinationLocation

Output:

- walkingDistanceM
- walkingTimeMin

Uses OneMap routing.

---

## CarparkRepository

### getNearbyCarparks

Input:

- destinationLocation
- radiusM

Output:

- list of Carpark objects

### getCarparkById

Input:

- carparkId

Output:

- Carpark or null

---

## FeeCalculator

### calculateFee

Input:

- carpark
- arrivalTime
- departureTime

Output:

- estimated parking fee in SGD
- null if reliable rate information is unavailable

---

## AvailabilityService

### getCurrentAvailability

Input:

- carparkId
- lotType

Output:

- Availability or null

Availability contains:

- availableLots
- totalLots
- timestamp
- isStale

---

## HistoricalAvailabilityRepository

### saveAvailabilityRecord

Input:

- carparkId
- lotType
- availableLots
- totalLots
- timestamp

Output:

- none

### getHistoricalRecords

Input:

- carparkId
- lotType
- arrivalTime

Output:

- list of HistoricalAvailability records

---

## BusynessEstimator

### estimateBusyness

Input:

- historical availability records
- expected arrival time

Output:

- ExpectedBusyness or null

ExpectedBusyness contains:

- occupancyPercentage
- level

Levels:

- LOW
- MODERATE
- HIGH

---

## EVChargingService

### getChargingInformation

Input:

- carpark

Output:

- EVCharging information

EVCharging contains:

- supported
- availableChargers

---

## RankingEngine

### rankCarparks

Input:

- list of SearchResult objects
- SearchPreference

Output:

- ordered list of SearchResult objects

Responsibilities:

- apply mandatory filters
- calculate composite score
- handle unavailable ranking factors
- apply tie-breaker
- assign rank

---

## HistoricalAvailabilityCollector

Runs periodically in the background.

Responsibilities:

- retrieve live availability
- convert responses to the normalised Availability format
- store timestamped observations in MySQL