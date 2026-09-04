Voice of Customer Platform

An AI-powered web application that collects customer feedback, analyses it with Google Gemini, and converts it into actionable business insights. The platform helps organisations understand customer sentiment, identify emerging issues, prioritise complaints, and improve decision-making through a unified dashboard.

Project Objective

Traditional feedback systems mainly store reviews and display basic ratings. This project goes further by combining feedback management, artificial intelligence, analytics, and action tracking. It enables organisations to understand what customers are saying, determine which issues require immediate attention, and monitor changes in customer experience over time.

Key Features

Feedback collection through web forms, QR codes, CSV files, and a REST API

Customer registration, login, profile, and review history

Role-based access for administrators, managers, and agents

AI-based sentiment, emotion, topic, priority, and department identification

Review quality and authenticity verification

Category-based public reviews with privacy protection

Interactive dashboard with filters, KPIs, and charts

Silent Customer Detector using sales and review volumes

Customer Feedback Journey Timeline

Emerging Issue Radar for week-over-week issue detection

Voice Health Score with performance trends

What-If Simulator for estimating the effect of resolving issues

AI-generated business recommendations

Department-wise action queue with status tracking

Weekly executive summaries with saved history

Filtered CSV and JSON exports

How It Works

A customer submits feedback through the web form, QR code, CSV import, or API.

The system validates the submission and checks its quality and authenticity.

Gemini analyses the review to identify its sentiment, emotion, topic, priority, and relevant department.

The original review and the analysed results are stored separately in the database.

The dashboard converts the stored data into charts, KPIs, trends, alerts, and action queues.

Managers use the recommendations, simulations, and weekly summaries to support decisions.

System Design

The platform uses a layered design that separates the user interface, application logic, Gemini communication, advanced analytics, data management, and database storage. This separation makes the system easier to test, maintain, and expand.

Major Intelligent Features

Silent Customer Detector

Compares product sales with the number of reviews received. A product with high sales but very little feedback is marked as a silent-customer risk because the organisation does not have enough information about those customers' experiences.

Emerging Issue Radar

Compares the frequency of feedback topics in the current week with the previous week. Issues that increase by 20% or more are highlighted so that the organisation can respond before they become widespread.

Voice Health Score

Provides a single score from 0 to 100 representing the overall condition of customer experience.

Measure

Weight

Sentiment balance

35%

Average rating

25%

Resolution rate

20%

Review quality

10%

Engagement depth

10%

The score is compared with the previous period and classified as improving, stable, or declining.

What-If Simulator

Estimates how the Voice Health Score could change if a selected percentage of an issue were resolved. The simulation uses temporary data and does not modify actual customer records.

Recommendation Engine

Uses Gemini to produce focused business recommendations from aggregated feedback statistics. Recommendations are cached to avoid unnecessary API requests.

Department-wise Action Queue

Groups unresolved feedback according to department, issue, and priority. Staff can update each group as Pending, In Progress, or Resolved.

Weekly Executive Summary

Generates a structured weekly report covering positive trends, major concerns, emerging issues, risks, and recommended actions. Previous summaries are retained for comparison.

