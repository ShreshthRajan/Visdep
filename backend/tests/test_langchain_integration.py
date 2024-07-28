import requests
import os

def upload_repository(repo_url):
    response = requests.post(
        "http://127.0.0.1:8000/api/upload_repo",
        json={"repo_url": repo_url}
    )
    print("Uploading repository...")
    print(response.json())

def query_jamba(query, context):
    response = requests.post(
        "http://127.0.0.1:8000/api/query",
        json={"query": query, "context": context}
    )
    print(f"Querying: {query}")
    print(response.json())

if __name__ == "__main__":
    repo_url = "https://github.com/ShreshthRajan/tensorflow"
    upload_repository(repo_url)
    
    queries = [
        {
            "query": "How do the core components of TensorFlow (e.g., tensorflow/core, tensorflow/python, tensorflow/compiler) interact during the execution of a computational graph? Provide an example illustrating the flow of data and control between these components.",
            "context": "{\"TensorFlow\": {\"README.md\": {\"functions\": [], \"classes\": [], \"imports\": []}}}"
        },
        {
            "query": "What are the differences between the TensorFlow eager execution mode and graph execution mode? How is each mode implemented, and what are the trade-offs in terms of performance and flexibility?",
            "context": "{\"TensorFlow\": {\"tensorflow/python/framework/ops.py\": {\"functions\": [], \"classes\": [], \"imports\": []}}}"
        },
        {
            "query": "Explain the implementation details of tf.distribute.MirroredStrategy. How does it handle synchronization of variables and gradients across multiple GPUs? What are the underlying communication mechanisms used?",
            "context": "{\"TensorFlow\": {\"tensorflow/python/distribute/mirrored_strategy.py\": {\"functions\": [], \"classes\": [], \"imports\": []}}}"
        },
        {
            "query": "Describe the process of creating a custom TensorFlow operation. What files and methods are involved in defining, registering, and executing a custom operation? Provide a detailed example, including both the Python and C++ components.",
            "context": "{\"TensorFlow\": {\"tensorflow/python/framework/op_def_registry.py\": {\"functions\": [], \"classes\": [], \"imports\": []}, \"tensorflow/core/framework/op.h\": {\"functions\": [], \"classes\": [], \"imports\": []}}}"
        },
        {
            "query": "Examine the implementation of the tf.GradientTape class in tensorflow/python/eager/backprop.py. How does it record operations for automatic differentiation? What optimizations are employed to ensure efficient gradient computation?",
            "context": "{\"TensorFlow\": {\"tensorflow/python/eager/backprop.py\": {\"functions\": [\"GradientTape\"], \"classes\": [], \"imports\": []}}}"
        },
        {
            "query": "How is the tf.data.Dataset API implemented? What are the key classes and methods involved? Discuss the role of tensorflow/python/data/ops/dataset_ops.py and tensorflow/python/data/experimental/ops in this implementation.",
            "context": "{\"TensorFlow\": {\"tensorflow/python/data/ops/dataset_ops.py\": {\"functions\": [], \"classes\": [], \"imports\": []}, \"tensorflow/python/data/experimental/ops\": {\"functions\": [], \"classes\": [], \"imports\": []}}}"
        },
        {
            "query": "Describe the integration of TensorFlow with hardware accelerators like GPUs and TPUs. How does the TensorFlow runtime decide whether to place operations on a CPU, GPU, or TPU? What files and classes are responsible for this decision-making process?",
            "context": "{\"TensorFlow\": {\"tensorflow/core/common_runtime/device_set.h\": {\"functions\": [], \"classes\": [], \"imports\": []}}}"
        },
        {
            "query": "What techniques does TensorFlow use to optimize computational graphs before execution? Discuss the roles of tensorflow/core/grappler and tensorflow/compiler/xla in graph optimization.",
            "context": "{\"TensorFlow\": {\"tensorflow/core/grappler\": {\"functions\": [], \"classes\": [], \"imports\": []}, \"tensorflow/compiler/xla\": {\"functions\": [], \"classes\": [], \"imports\": []}}}"
        },
        {
            "query": "How does TensorFlow handle memory management and data caching to optimize performance? Discuss the implementation details in tensorflow/core/common_runtime and tensorflow/core/framework.",
            "context": "{\"TensorFlow\": {\"tensorflow/core/common_runtime\": {\"functions\": [], \"classes\": [], \"imports\": []}, \"tensorflow/core/framework\": {\"functions\": [], \"classes\": [], \"imports\": []}}}"
        },
        {
            "query": "How does TensorFlow achieve parallelism in both computation and data input pipelines? Discuss the role of multi-threading, multi-processing, and asynchronous execution in TensorFlow's performance optimization strategies.",
            "context": "{\"TensorFlow\": {\"tensorflow/core/kernels\": {\"functions\": [], \"classes\": [], \"imports\": []}, \"tensorflow/core/util\": {\"functions\": [], \"classes\": [], \"imports\": []}}}"
        },
        {
            "query": "In tensorflow/python/distribute/distribute_lib.py, what is the role of the _DefaultDistributionStrategy class? How does it interact with other distribution strategies like MirroredStrategy and MultiWorkerMirroredStrategy?",
            "context": "{\"TensorFlow\": {\"tensorflow/python/distribute/distribute_lib.py\": {\"functions\": [], \"classes\": [\"_DefaultDistributionStrategy\"], \"imports\": []}}}"
        },
        {
            "query": "How does tensorflow/core/common_runtime/optimization_registry.h contribute to the optimization process? What are the key classes and methods defined in this file, and how do they interact with other components in the optimization pipeline?",
            "context": "{\"TensorFlow\": {\"tensorflow/core/common_runtime/optimization_registry.h\": {\"functions\": [], \"classes\": [], \"imports\": []}}}"
        },
        {
            "query": "How does the tensorflow/compiler module interact with the tensorflow/core and tensorflow/python modules during the compilation and execution of a TensorFlow graph? Provide a detailed flow of function calls and data transformations.",
            "context": "{\"TensorFlow\": {\"tensorflow/compiler\": {\"functions\": [], \"classes\": [], \"imports\": []}, \"tensorflow/core\": {\"functions\": [], \"classes\": [], \"imports\": []}, \"tensorflow/python\": {\"functions\": [], \"classes\": [], \"imports\": []}}}"
        }
    ]
    
    for q in queries:
        query_jamba(q["query"], q["context"])
