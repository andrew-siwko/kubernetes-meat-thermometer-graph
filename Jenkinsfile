pipeline {
    agent { label 'docker-builder' }

    environment {
        REGISTRY = 'kregistry.siwko.org:5000'
        IMAGE = "${REGISTRY}/meat-thermometer-graph"
        IMAGE_TAG = "${env.BUILD_NUMBER}"
    }

    stages {
        stage('Build') {
            steps {
                sh "docker build --provenance=false --sbom=false -f Dockerfile -t ${IMAGE}:${IMAGE_TAG} -t ${IMAGE}:latest ."
            }
        }
        stage('Push') {
            steps {
                sh "docker push ${IMAGE}:${IMAGE_TAG}"
                sh "docker push ${IMAGE}:latest"
            }
        }
        stage('Deploy') {
            steps {
                sh "kubectl apply -f k8s/pvc.yaml"
                sh "kubectl apply -f k8s/graph-server-deployment.yaml"
                sh "kubectl apply -f k8s/graph-cronjob.yaml"
                sh "kubectl rollout restart deployment/meat-thermometer-graph-server"
            }
        }
    }
}
