#!/usr/bin/env python3
"""
RAS Analytics and Reporting Engine

Provides aggregated statistics, trend analysis, and reporting for RAS data.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class RASAnalyticsEngine:
    """
    Analytics engine for RAS data.
    
    Provides:
    - Error rate analysis
    - Trend detection
    - Component failure analysis
    - Time-based aggregations
    - Health scoring
    """
    
    def __init__(self, log_service_handler=None):
        """
        Initialize analytics engine.
        
        Args:
            log_service_handler: RAS LogService handler for data access
        """
        self.log_service = log_service_handler
        
        # In-memory analytics cache
        self.analytics_cache = {
            "error_counts": defaultdict(int),
            "component_failures": defaultdict(int),
            "severity_distribution": defaultdict(int),
            "hourly_counts": defaultdict(int),
            "daily_counts": defaultdict(int)
        }
        
        logger.info("RAS Analytics Engine initialized")
    
    def analyze_error_trends(
        self,
        time_window_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Analyze error trends over time window.
        
        Args:
            time_window_hours: Time window in hours
            
        Returns:
            dict: Trend analysis results
        """
        if not self.log_service:
            return {"error": "LogService not available"}
        
        # Get entries from time window
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=time_window_hours)
        
        hourly_errors = defaultdict(int)
        severity_trend = defaultdict(lambda: defaultdict(int))
        component_errors = defaultdict(int)
        
        # Analyze each entry
        try:
            entries_path = self.log_service.entries_fs_path
            
            for entry_dir in entries_path.iterdir():
                if not entry_dir.is_dir() or entry_dir.name == "__pycache__":
                    continue
                
                # Read entry
                index_file = entry_dir / "index.json"
                if not index_file.exists():
                    continue
                
                with open(index_file, 'r') as f:
                    entry = json.load(f)
                
                # Parse timestamp
                created = datetime.fromisoformat(entry.get("Created", "").replace("Z", "+00:00"))
                if created < cutoff_time:
                    continue
                
                # Aggregate by hour
                hour_key = created.strftime("%Y-%m-%d %H:00")
                hourly_errors[hour_key] += 1
                
                # Aggregate by severity
                severity = entry.get("Severity", "OK")
                severity_trend[hour_key][severity] += 1
                
                # Aggregate by component
                oem_data = entry.get("Oem", {}).get("RasProto", {})
                component = oem_data.get("FRUId", "Unknown")
                component_errors[component] += 1
        
        except Exception as e:
            logger.error(f"Error analyzing trends: {e}")
            return {"error": str(e)}
        
        # Calculate trend direction
        if len(hourly_errors) >= 2:
            hours = sorted(hourly_errors.keys())
            recent_half = hours[len(hours)//2:]
            older_half = hours[:len(hours)//2]
            
            recent_avg = sum(hourly_errors[h] for h in recent_half) / len(recent_half)
            older_avg = sum(hourly_errors[h] for h in older_half) / len(older_half)
            
            if recent_avg > older_avg * 1.2:
                trend = "increasing"
            elif recent_avg < older_avg * 0.8:
                trend = "decreasing"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"
        
        return {
            "time_window_hours": time_window_hours,
            "total_errors": sum(hourly_errors.values()),
            "trend": trend,
            "hourly_distribution": dict(hourly_errors),
            "severity_trend": {k: dict(v) for k, v in severity_trend.items()},
            "component_failures": dict(component_errors),
            "analyzed_at": datetime.now(timezone.utc).isoformat()
        }
    
    def get_component_health_scores(self) -> Dict[str, Any]:
        """
        Calculate health scores for components based on RAS data.
        
        Returns:
            dict: Component health scores
        """
        if not self.log_service:
            return {"error": "LogService not available"}
        
        component_data = defaultdict(lambda: {
            "total_errors": 0,
            "critical_errors": 0,
            "warning_errors": 0,
            "last_error": None,
            "health_score": 100.0
        })
        
        try:
            entries_path = self.log_service.entries_fs_path
            
            for entry_dir in entries_path.iterdir():
                if not entry_dir.is_dir() or entry_dir.name == "__pycache__":
                    continue
                
                index_file = entry_dir / "index.json"
                if not index_file.exists():
                    continue
                
                with open(index_file, 'r') as f:
                    entry = json.load(f)
                
                # Get component ID
                oem_data = entry.get("Oem", {}).get("RasProto", {})
                component = oem_data.get("FRUId", "Unknown")
                
                # Update component stats
                component_data[component]["total_errors"] += 1
                
                severity = entry.get("Severity", "OK")
                if severity == "Critical":
                    component_data[component]["critical_errors"] += 1
                elif severity == "Warning":
                    component_data[component]["warning_errors"] += 1
                
                # Track last error time
                created = entry.get("Created")
                if (not component_data[component]["last_error"] or 
                    created > component_data[component]["last_error"]):
                    component_data[component]["last_error"] = created
            
            # Calculate health scores
            for component, data in component_data.items():
                # Start with perfect score
                score = 100.0
                
                # Deduct for errors
                score -= data["critical_errors"] * 10.0
                score -= data["warning_errors"] * 3.0
                score -= data["total_errors"] * 0.5
                
                # Bonus for no recent errors
                if data["last_error"]:
                    last_error_time = datetime.fromisoformat(
                        data["last_error"].replace("Z", "+00:00")
                    )
                    hours_since = (datetime.now(timezone.utc) - last_error_time).total_seconds() / 3600
                    
                    if hours_since > 168:  # 1 week
                        score += 5.0
                
                # Clamp score
                data["health_score"] = max(0.0, min(100.0, score))
        
        except Exception as e:
            logger.error(f"Error calculating health scores: {e}")
            return {"error": str(e)}
        
        return {
            "components": dict(component_data),
            "overall_health": sum(d["health_score"] for d in component_data.values()) / len(component_data) if component_data else 100.0,
            "analyzed_at": datetime.now(timezone.utc).isoformat()
        }
    
    def get_severity_distribution(self) -> Dict[str, Any]:
        """Get distribution of errors by severity"""
        if not self.log_service:
            return {"error": "LogService not available"}
        
        severity_counts = Counter()
        
        try:
            entries_path = self.log_service.entries_fs_path
            
            for entry_dir in entries_path.iterdir():
                if not entry_dir.is_dir() or entry_dir.name == "__pycache__":
                    continue
                
                index_file = entry_dir / "index.json"
                if not index_file.exists():
                    continue
                
                with open(index_file, 'r') as f:
                    entry = json.load(f)
                
                severity = entry.get("Severity", "OK")
                severity_counts[severity] += 1
        
        except Exception as e:
            logger.error(f"Error getting severity distribution: {e}")
            return {"error": str(e)}
        
        total = sum(severity_counts.values())
        
        return {
            "total_entries": total,
            "distribution": dict(severity_counts),
            "percentages": {
                sev: f"{(count / total * 100):.1f}%" 
                for sev, count in severity_counts.items()
            } if total > 0 else {},
            "analyzed_at": datetime.now(timezone.utc).isoformat()
        }
    
    def get_summary_report(self) -> Dict[str, Any]:
        """Generate comprehensive summary report"""
        return {
            "report_type": "RAS Summary Report",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "error_trends": self.analyze_error_trends(time_window_hours=24),
            "component_health": self.get_component_health_scores(),
            "severity_distribution": self.get_severity_distribution()
        }
    
    def export_analytics_data(self, output_path: Path) -> bool:
        """
        Export analytics data to file.
        
        Args:
            output_path: Path to output file
            
        Returns:
            bool: True if successful
        """
        try:
            report = self.get_summary_report()
            
            with open(output_path, 'w') as f:
                json.dump(report, f, indent=2)
            
            logger.info(f"Analytics data exported to {output_path}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to export analytics: {e}")
            return False
