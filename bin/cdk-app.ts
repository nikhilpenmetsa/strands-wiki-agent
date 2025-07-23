#!/usr/bin/env node
import { App } from "aws-cdk-lib";
import { EncyclopediaAgentStack } from "../lib/encyclopedia-agent-stack";
import { FrontendStack } from "../lib/frontend-stack";

const app = new App();

// Deploy encyclopedia agent stack with knowledge base ID and guardrail
const encyclopediaStack = new EncyclopediaAgentStack(app, "EncyclopediaAgentStack", {
  knowledgeBaseId: "3UWWAYOA4C",
  guardrailId: "zvun1rhffma7",
});

// Deploy frontend stack
new FrontendStack(app, "FrontendStack");