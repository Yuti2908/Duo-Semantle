import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as apigwv2 from 'aws-cdk-lib/aws-apigatewayv2';
import * as integrations from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as path from 'path';

export class DuoSemantleInfraStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const wordsBucket = new s3.Bucket(this, 'WordsBucket', {
      bucketName: 'duo-semantle-data-saransh-cdk',
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    new s3deploy.BucketDeployment(this, 'DeployWords', {
      sources: [s3deploy.Source.asset(path.join(__dirname, '..', 'data'))],
      destinationBucket: wordsBucket,
    });

    const validatorFn = new lambda.Function(this, 'WordValidatorFunction', {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'lambda_function.handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '..', 'lambda')),
      timeout: cdk.Duration.seconds(10),
      memorySize: 256,
      environment: {
        BUCKET_NAME: wordsBucket.bucketName,
        WORDS_KEY: 'words.txt',
      },
    });

    wordsBucket.grantRead(validatorFn);

    const httpApi = new apigwv2.HttpApi(this, 'DuoSemantleApi', {
      apiName: 'duo-semantle-api-cdk',
    });

    httpApi.addRoutes({
      path: '/{proxy+}',
      methods: [apigwv2.HttpMethod.ANY],
      integration: new integrations.HttpLambdaIntegration('LambdaIntegration', validatorFn),
    });

    new cdk.CfnOutput(this, 'ApiUrl', {
      value: httpApi.apiEndpoint,
    });

    const embeddingsBucket = new s3.Bucket(this, 'EmbeddingsBucket', {
      bucketName: 'duo-semantle-embeddings-saransh-cdk',
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    new s3deploy.BucketDeployment(this, 'DeployEmbeddings', {
      sources: [s3deploy.Source.asset(path.join(__dirname, '..', 'data-embeddings'))],
      destinationBucket: embeddingsBucket,
      destinationKeyPrefix: 'embeddings',
      memoryLimit: 1024,
      ephemeralStorageSize: cdk.Size.mebibytes(1024),
    });

    const pandasLayer = lambda.LayerVersion.fromLayerVersionArn(
      this,
      'AWSSDKPandasLayer',
      'arn:aws:lambda:ap-south-1:336392948345:layer:AWSSDKPandas-Python312:31'
    );

    const scoringFn = new lambda.Function(this, 'ScoringFunction', {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'lambda_function.handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '..', 'scoring-lambda')),
      timeout: cdk.Duration.seconds(15),
      memorySize: 512,
      layers: [pandasLayer],
      environment: {
        BUCKET_NAME: embeddingsBucket.bucketName,
        EMBEDDINGS_PREFIX: 'embeddings/',
      },
    });

    embeddingsBucket.grantRead(scoringFn);

    httpApi.addRoutes({
      path: '/score',
      methods: [apigwv2.HttpMethod.ANY],
      integration: new integrations.HttpLambdaIntegration('ScoringLambdaIntegration', scoringFn),
    });

    new cdk.CfnOutput(this, 'ScoringApiUrl', {
      value: `${httpApi.apiEndpoint}/score`,
    });

    const targetsTable = new dynamodb.Table(this, 'TargetsTable', {
      tableName: 'duo-semantle-targets',
      partitionKey: { name: 'pk', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'date', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    const targetSelectorFn = new lambda.Function(this, 'TargetSelectorFunction', {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'lambda_function.handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '..', 'target-selector-lambda')),
      timeout: cdk.Duration.seconds(300),
      memorySize: 3008,
      layers: [pandasLayer],
      environment: {
        WORDS_BUCKET: wordsBucket.bucketName,
        EMBEDDINGS_BUCKET: embeddingsBucket.bucketName,
        EMBEDDINGS_PREFIX: 'embeddings/',
        TABLE_NAME: targetsTable.tableName,
        POOL_KEY: 'target_pool.txt',
      },
    });

    wordsBucket.grantRead(targetSelectorFn);
    embeddingsBucket.grantRead(targetSelectorFn);
    targetsTable.grantReadWriteData(targetSelectorFn);

    const dailyRule = new events.Rule(this, 'DailyTargetSelectionRule', {
      schedule: events.Schedule.cron({ minute: '0', hour: '0' }),
    });
    dailyRule.addTarget(new targets.LambdaFunction(targetSelectorFn));

    new cdk.CfnOutput(this, 'TargetsTableName', {
      value: targetsTable.tableName,
    });

    const sharedLayer = new lambda.LayerVersion(this, 'SharedCommonLayer', {
      code: lambda.Code.fromAsset(path.join(__dirname, '..', 'shared-layer')),
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_12],
      description: 'Shared validation, scoring, and embedding-lookup logic',
    });

    const guessesTable = new dynamodb.Table(this, 'GuessesTable', {
      tableName: 'duo-semantle-guesses',
      partitionKey: { name: 'session_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'timestamp', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    const guessFn = new lambda.Function(this, 'GuessFunction', {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'lambda_function.handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '..', 'guess-lambda')),
      timeout: cdk.Duration.seconds(15),
      memorySize: 512,
      layers: [pandasLayer, sharedLayer],
      environment: {
        WORDS_BUCKET: wordsBucket.bucketName,
        WORDS_KEY: 'words.txt',
        EMBEDDINGS_BUCKET: embeddingsBucket.bucketName,
        EMBEDDINGS_PREFIX: 'embeddings/',
        TARGETS_TABLE_NAME: targetsTable.tableName,
        GUESSES_TABLE_NAME: guessesTable.tableName,
      },
    });

    wordsBucket.grantRead(guessFn);
    embeddingsBucket.grantRead(guessFn);
    targetsTable.grantReadData(guessFn);
    guessesTable.grantReadWriteData(guessFn);

    httpApi.addRoutes({
      path: '/guess',
      methods: [apigwv2.HttpMethod.ANY],
      integration: new integrations.HttpLambdaIntegration('GuessLambdaIntegration', guessFn),
    });

    new cdk.CfnOutput(this, 'GuessApiUrl', {
      value: `${httpApi.apiEndpoint}/guess`,
    });

    new cdk.CfnOutput(this, 'GuessesTableName', {
      value: guessesTable.tableName,
    });

    // --- Frontend hosting slice ---

    const frontendBucket = new s3.Bucket(this, 'FrontendBucket', {
      bucketName: 'duo-semantle-frontend-saransh-cdk',
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    const distribution = new cloudfront.Distribution(this, 'FrontendDistribution', {
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessControl(frontendBucket),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
      },
      defaultRootObject: 'index.html',
    });

    new s3deploy.BucketDeployment(this, 'DeployFrontend', {
      sources: [s3deploy.Source.asset(path.join(__dirname, '..', 'frontend'))],
      destinationBucket: frontendBucket,
      distribution,
      distributionPaths: ['/*'],
    });

    new cdk.CfnOutput(this, 'FrontendUrl', {
      value: `https://${distribution.distributionDomainName}`,
    });
  }
}
