#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib/core';
import { FridgeFlyerStack } from '../lib/fridge-flyer-stack';

const app = new cdk.App();
new FridgeFlyerStack(app, 'FridgeFlyerStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION || 'ap-northeast-1'
  },
});
