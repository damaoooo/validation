import os

# 给定的文件路径
file_path = 'sbom/python/raw/trivy_root_workspace_validation_python_nicfit_eyeD3_0.9.x_poetry.lock.json'

# 获取上一级目录
parent_dir = os.path.dirname(file_path)

# 获取上上一级目录
grandparent_dir = os.path.dirname(parent_dir)

# 提取上一级和上上一级目录的名称
parent_dir_name = os.path.basename(parent_dir)
grandparent_dir_name = os.path.basename(os.path.dirname(os.path.dirname(file_path)))

print(f"上一级目录名称: {parent_dir_name}")
print(f"上上一级目录名称: {grandparent_dir_name}")
