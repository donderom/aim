import { RecordRanges, AimFlatObjectBase } from 'types/core/AimObjects';
import { Context } from 'types/core/shared';

export type ProcessInterceptor = (...arg: any) => any;

export interface IQueryableData {
  ranges?: RecordRanges;
}

export interface ProcessedData {
  objectList: AimFlatObjectBase[];
  queryable_data: IQueryableData;
  additionalData: {
    params: string[];
    sequenceInfo: string[];
    modifiers: string[];
  };
}

export type ObjectHashCreator = {
  hash: string;
  name?: string;
  context?: Context;
  step?: number;
  index?: number;
};
