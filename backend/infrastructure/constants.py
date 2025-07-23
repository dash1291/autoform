# ECS Infrastructure Constants

# Default Launch Configuration
DEFAULT_LAUNCH_TYPE = "EC2"
DEFAULT_NETWORK_MODE = "bridge"  # Use bridge mode for better performance and cost

# EC2 Instance Configuration
DEFAULT_EC2_INSTANCE_TYPE = "t3a.small"  # 2 vCPUs, 2GB RAM
DEFAULT_EC2_MIN_SIZE = 1
DEFAULT_EC2_MAX_SIZE = 3   # Reasonable max for most workloads
DEFAULT_EC2_DESIRED_CAPACITY = 1
DEFAULT_EC2_USE_SPOT = True
DEFAULT_EC2_SPOT_MAX_PRICE = ""
DEFAULT_EC2_KEY_NAME = ""
DEFAULT_CAPACITY_PROVIDER_TARGET_CAPACITY = 80  # Maximum utilization

# Container Configuration
DEFAULT_CPU = 256
DEFAULT_MEMORY = 512
DEFAULT_DISK_SIZE = 21
DEFAULT_CONTAINER_PORT = 3000

# Networking Configuration
DEFAULT_DYNAMIC_PORT_RANGE_START = 32768
DEFAULT_DYNAMIC_PORT_RANGE_END = 65535

# EC2 Instance Resources (in ECS CPU units and MB)
# ECS CPU units: 1024 = 1 vCPU
# Reserve ~20% for system overhead and ECS agent
INSTANCE_RESOURCES = {
    "t3a.nano": {"cpu": 820, "memory": 409},      # 1 vCPU, 0.5GB (80% available)
    "t3a.micro": {"cpu": 820, "memory": 819},     # 1 vCPU, 1GB
    "t3a.small": {"cpu": 1638, "memory": 1638},   # 2 vCPU, 2GB  
    "t3a.medium": {"cpu": 1638, "memory": 3277},  # 2 vCPU, 4GB
    "t3a.large": {"cpu": 3277, "memory": 6553},   # 4 vCPU, 8GB
    "t3a.xlarge": {"cpu": 6553, "memory": 13107}, # 8 vCPU, 16GB
}

def get_recommended_instance_type(cpu: int, memory: int, min_tasks: int = 2, network_mode: str = "bridge") -> str:
    """
    Get recommended EC2 instance type that can run at least min_tasks containers.
    
    Args:
        cpu: CPU units per task (256, 512, 1024, etc.)
        memory: Memory per task in MB
        min_tasks: Minimum number of tasks the instance should support
        network_mode: Network mode (bridge/awsvpc) affects capacity limits
        
    Returns:
        Recommended EC2 instance type
    """
    # Find smallest instance that can handle the workload
    for instance_type in INSTANCE_RESOURCES.keys():
        capacity = calculate_task_capacity(instance_type, cpu, memory, network_mode)
        if capacity >= min_tasks:
            return instance_type
    
    # If no instance can handle it, return largest
    return "t3a.xlarge"

# Monthly costs (USD) for t3a instances in us-east-1
MONTHLY_COSTS = {
    "t3a.nano": {"on_demand": 3.80, "spot_avg": 1.52},
    "t3a.micro": {"on_demand": 7.59, "spot_avg": 3.04},
    "t3a.small": {"on_demand": 15.18, "spot_avg": 6.07},
    "t3a.medium": {"on_demand": 30.37, "spot_avg": 12.15},
    "t3a.large": {"on_demand": 60.74, "spot_avg": 24.30},
    "t3a.xlarge": {"on_demand": 121.47, "spot_avg": 48.59},
}

def get_monthly_cost(instance_type: str, use_spot: bool = True) -> float:
    """Get estimated monthly cost for an instance type."""
    if instance_type not in MONTHLY_COSTS:
        return 0.0
    
    cost_type = "spot_avg" if use_spot else "on_demand"
    return MONTHLY_COSTS[instance_type][cost_type]

def calculate_task_capacity(instance_type: str, task_cpu: int, task_memory: int, network_mode: str = "bridge") -> int:
    """Calculate how many tasks can fit on an instance type.
    
    In bridge mode: Limited only by CPU/memory resources
    In awsvpc mode: Limited by ENI availability (max 2-3 tasks on t3a instances)
    """
    if instance_type not in INSTANCE_RESOURCES:
        return 0
    
    resources = INSTANCE_RESOURCES[instance_type]
    cpu_capacity = resources["cpu"] // task_cpu
    memory_capacity = resources["memory"] // task_memory
    resource_capacity = min(cpu_capacity, memory_capacity)
    
    # In awsvpc mode, ENI limits apply
    if network_mode == "awsvpc":
        # ENI limits for common instance types (primary ENI + task ENIs)
        eni_limits = {
            "t3a.nano": 1,      # 2 ENIs - 1 primary = 1 task
            "t3a.micro": 1,     # 2 ENIs - 1 primary = 1 task
            "t3a.small": 2,     # 3 ENIs - 1 primary = 2 tasks
            "t3a.medium": 2,    # 3 ENIs - 1 primary = 2 tasks
            "t3a.large": 2,     # 3 ENIs - 1 primary = 2 tasks
            "t3a.xlarge": 3,    # 4 ENIs - 1 primary = 3 tasks
        }
        eni_capacity = eni_limits.get(instance_type, resource_capacity)
        return min(resource_capacity, eni_capacity)
    
    # In bridge mode, no ENI limits
    return resource_capacity