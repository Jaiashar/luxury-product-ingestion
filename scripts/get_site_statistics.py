import os
import boto3
from collections import defaultdict

# Initialize DynamoDB client
dynamodb = boto3.client('dynamodb', region_name='us-east-1')
table_name = os.environ['DYNAMODB_TABLE_NAME']

# Paginate through the scan results
paginator = dynamodb.get_paginator('scan')
response_iterator = paginator.paginate(
    TableName=table_name,
    ProjectionExpression='site'
)

site_counts = defaultdict(int)

# Count items by site
for page in response_iterator:
    for item in page['Items']:
        site = item.get('site', {}).get('S', 'unknown')
        site_counts[site] += 1

# Print results
print("📊 Product Count by Site")
print("========================")
for site, count in sorted(site_counts.items(), key=lambda x: x[1], reverse=True):
    print(f"{site}: {count}")
