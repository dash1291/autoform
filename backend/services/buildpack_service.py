import logging
from typing import Optional, Dict, List
from pathlib import Path

logger = logging.getLogger(__name__)


class BuildpackService:
    """Service for managing Cloud Native Buildpack configuration"""
    
    @classmethod
    def get_builder(cls) -> str:
        """Get the CNB builder to use"""
        return "heroku/builder:24"
    
    @classmethod
    def get_available_builders(cls) -> List[Dict[str, str]]:
        """Get list of available builders"""
        return [
            {
                "id": "heroku/builder:24",
                "name": "Heroku builder",
                "description": "Auto-detects Node.js, Python, Java, Go, .NET applications"
            }
        ]
    
    @classmethod
    def should_use_buildpack(cls, project_path: str, subdirectory: Optional[str] = None) -> bool:
        """
        Check if buildpack should be used (no Dockerfile present)
        
        Args:
            project_path: Path to the cloned project
            subdirectory: Optional subdirectory within the project
            
        Returns:
            True if buildpack should be used, False if Dockerfile exists
        """
        base_path = Path(project_path)
        if subdirectory:
            base_path = base_path / subdirectory
        
        dockerfile_path = base_path / "Dockerfile"
        has_dockerfile = dockerfile_path.exists()
        
        if has_dockerfile:
            logger.info(f"Dockerfile found at {dockerfile_path}")
        else:
            logger.info("No Dockerfile found, will use Cloud Native Buildpack")
            
        return not has_dockerfile
    
    @classmethod
    def get_builder_for_project(cls, project_config: Optional[Dict] = None) -> str:
        """
        Get the builder for a project
        
        Args:
            project_config: Optional project configuration (currently unused)
            
        Returns:
            Builder image to use
        """
        # Always use the Google Cloud builder - it handles detection automatically
        return cls.get_builder()
    
    @classmethod
    def get_pack_build_command(cls, image_name: str, builder: str, path: str, env_vars: Dict[str, str] = None) -> str:
        """
        Generate the pack build command
        
        Args:
            image_name: Name of the image to build
            builder: Builder image to use
            path: Path to build from
            env_vars: Environment variables (optional, handled separately)
            
        Returns:
            The pack build command string
        """
        return f"pack build {image_name} --builder {builder} --path {path}"