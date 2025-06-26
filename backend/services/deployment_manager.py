import asyncio
import logging
from typing import Dict, Set, Optional
from datetime import datetime
import threading

logger = logging.getLogger(__name__)


class DeploymentManager:
    """Manages deployment state and background tasks"""

    def __init__(self):
        self._active_deployments: Dict[str, str] = {}  # project_id -> deployment_id
        self._aborted_deployments: Set[
            str
        ] = set()  # project_ids that have been aborted
        self._deployment_statuses: Dict[str, str] = {}  # deployment_id -> status
        self._lock = threading.Lock()

    def register_deployment(self, project_id: str, deployment_id: str) -> None:
        """Register a new deployment"""
        with self._lock:
            self._active_deployments[project_id] = deployment_id
            self._deployment_statuses[deployment_id] = "running"
            # Remove from aborted set if it was there
            self._aborted_deployments.discard(project_id)

        logger.info(f"Registered deployment {deployment_id} for project {project_id}")

    def complete_deployment(self, project_id: str) -> None:
        """Mark deployment as completed"""
        with self._lock:
            deployment_id = self._active_deployments.get(project_id)
            if deployment_id:
                self._deployment_statuses[deployment_id] = "completed"
                del self._active_deployments[project_id]

            # Remove from aborted set
            self._aborted_deployments.discard(project_id)

        logger.info(f"Completed deployment for project {project_id}")

    def abort_deployment(self, project_id: str) -> bool:
        """Abort an active deployment by project ID"""
        with self._lock:
            if project_id in self._active_deployments:
                deployment_id = self._active_deployments[project_id]
                self._aborted_deployments.add(project_id)
                self._deployment_statuses[deployment_id] = "aborted"
                logger.info(
                    f"Aborted deployment {deployment_id} for project {project_id}"
                )
                return True
            return False

    def abort_deployment_by_id(self, deployment_id: str, project_id: str) -> bool:
        """Abort a specific deployment by deployment ID"""
        with self._lock:
            # Check if this deployment is the active one for the project
            active_deployment_id = self._active_deployments.get(project_id)

            if active_deployment_id == deployment_id:
                # This is the active deployment, mark project as aborted
                self._aborted_deployments.add(project_id)
                del self._active_deployments[project_id]

            # Mark the specific deployment as aborted
            self._deployment_statuses[deployment_id] = "aborted"
            logger.info(
                f"Aborted specific deployment {deployment_id} for project {project_id}"
            )
            return True

    def is_deployment_aborted(self, deployment_id: str) -> bool:
        """Check if a specific deployment is aborted"""
        with self._lock:
            return self._deployment_statuses.get(deployment_id) == "aborted"

    def is_aborted(self, project_id: str) -> bool:
        """Check if deployment is aborted"""
        with self._lock:
            return project_id in self._aborted_deployments

    def get_deployment_status(self, deployment_id: str) -> Optional[str]:
        """Get deployment status"""
        with self._lock:
            return self._deployment_statuses.get(deployment_id)

    def get_active_deployment(self, project_id: str) -> Optional[str]:
        """Get active deployment ID for project"""
        with self._lock:
            return self._active_deployments.get(project_id)

    def is_deployment_active(self, project_id: str) -> bool:
        """Check if there's an active deployment for project"""
        with self._lock:
            return project_id in self._active_deployments

    def get_all_active_deployments(self) -> Dict[str, str]:
        """Get all active deployments"""
        with self._lock:
            return self._active_deployments.copy()

    def cleanup_old_statuses(self, max_age_hours: int = 24) -> None:
        """Clean up old deployment statuses"""
        # This is a simple implementation - in a real system you'd want
        # to track timestamps and clean up based on age
        with self._lock:
            completed_deployments = [
                dep_id
                for dep_id, status in self._deployment_statuses.items()
                if status in ["completed", "aborted", "failed"]
            ]

            # Keep only the last 100 completed deployments
            if len(completed_deployments) > 100:
                to_remove = completed_deployments[:-100]
                for dep_id in to_remove:
                    del self._deployment_statuses[dep_id]

                logger.info(f"Cleaned up {len(to_remove)} old deployment statuses")


# Global deployment manager instance
deployment_manager = DeploymentManager()
