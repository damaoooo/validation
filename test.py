import os

def extract_first_level_directory(path, base='/repo'):
    # 获取相对路径
    relative_path = os.path.relpath(path, base)
    # 拆分路径为各级目录
    parts = relative_path.split(os.sep)
    # 返回第一级目录名称
    return parts[0] if parts else None

# 示例路径
path = '/repo/javascript/kriskowal/q/package-lock.json'
# 提取第一级目录名称
first_level_dir = extract_first_level_directory(path)
print(first_level_dir)  # 输出：javascript