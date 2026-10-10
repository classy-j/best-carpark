# 2006-SCMD-O5
As there's a storage limit, kindly upload all deliverables format in .pdf and .jpeg format.

# Smart Carpark Recommendation System

SC2006 Software Engineering Project

## Overview

The Smart Carpark Recommendation System helps drivers identify suitable carparks near a selected destination based on factors including:

- Parking price
- Walking distance and time
- Current parking availability
- Predicted busyness at expected arrival time
- Carpark type
- Lot type
- EV charging availability

The system considers supported carparks within 1 km of the selected destination and ranks eligible carparks according to the user's preferences.

## Technology Stack

### Frontend
- HTML
- CSS
- JavaScript

### Backend
- Python
- FastAPI

### Database
- MySQL

### External Data Sources
- OneMap
- HDB / data.gov.sg
- LTA DataMall
- URA

## Repository Structure

```text
frontend/       Frontend application
backend/        Backend FastAPI application
tests/          Automated tests
docs/           Project documentation and diagrams