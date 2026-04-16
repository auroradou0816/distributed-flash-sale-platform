package com.hmdp.mq;

import com.hmdp.entity.VoucherOrder;
import lombok.extern.slf4j.Slf4j;
import org.apache.rocketmq.client.producer.SendResult;
import org.apache.rocketmq.spring.core.RocketMQTemplate;
import org.springframework.stereotype.Component;

import javax.annotation.Resource;

@Slf4j
@Component
public class SeckillOrderProducer {

    public static final String SECKILL_ORDER_TOPIC = "seckill-order-topic";

    @Resource
    private RocketMQTemplate rocketMQTemplate;

    public void send(VoucherOrder voucherOrder) {
        SendResult sendResult = rocketMQTemplate.syncSend(SECKILL_ORDER_TOPIC, voucherOrder);
        log.debug("发送秒杀订单消息成功，msgId={}", sendResult.getMsgId());
    }
}
